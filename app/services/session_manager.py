"""Session management backed by Supabase Postgres."""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple, Iterable, cast

from agents.items import TResponseInputItem
from agents.memory.session import SessionABC
from pydantic import ValidationError

from ..config import settings
from ..db import SessionLocal, models
from ..domain.schemas import (
    IntakeSubmission,
    InterviewRecord,
    PlanningContext,
    OptimizationResult,
)
from ..models.intake import IntakeRevision, IntakeStore
from ..models.timeline import (
    TimelineDetail,
    TimelineEvent,
    TimelineEventStatus,
    TimelineEventType,
    TimelineStage,
    TimelineState,
)
from .session_repository import SessionRepository

logger = logging.getLogger(__name__)

TimelineUpdatePayload = Dict[str, Any]
_cache_lock = threading.RLock()


def _utcnow() -> datetime:
    return datetime.now()


def _generate_session_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_part = uuid.uuid4().hex[:8]
    return f"{settings.default_session_prefix}{timestamp}_{unique_part}"


def _timeline_from_dict(data: Dict[str, Any]) -> TimelineState:
    state = TimelineState()
    if not data:
        return state

    state.version = int(data.get("version", 0))
    stage_value = data.get("current_stage")
    if stage_value:
        try:
            state.current_stage = TimelineStage(stage_value)
        except ValueError:
            logger.warning("Unknown timeline stage stored: %s", stage_value)
            state.current_stage = None

    events: list[TimelineEvent] = []
    for raw in data.get("events", []):
        try:
            timestamp_raw = raw.get("timestamp")
            if timestamp_raw:
                try:
                    timestamp_value = datetime.fromisoformat(timestamp_raw)
                except ValueError:
                    logger.warning(
                        "Invalid timeline timestamp stored: %s", timestamp_raw
                    )
                    timestamp_value = _utcnow()
            else:
                timestamp_value = _utcnow()
            event = TimelineEvent(
                id=str(raw.get("id", uuid.uuid4().hex)),
                type=TimelineEventType(raw.get("type", TimelineEventType.UPDATE.value)),
                title=str(raw.get("title", "")),
                stage=TimelineStage(raw.get("stage", TimelineStage.CONSULTATION.value)),
                status=TimelineEventStatus(
                    raw.get("status", TimelineEventStatus.PENDING.value)
                ),
                description=raw.get("description"),
                bank_name=raw.get("bankName") or raw.get("bank_name"),
                timestamp=timestamp_value,
                details=[
                    TimelineDetail(
                        label=str(item.get("label", "")),
                        value=str(item.get("value", "")),
                    )
                    for item in raw.get("details", [])
                ],
            )
            events.append(event)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to deserialize timeline event: %s", exc)
    state.events = events
    return state


def _intake_store_from_records(
    records: Iterable[models.SessionIntakeRevision],
) -> IntakeStore:
    store = IntakeStore()
    revisions: list[IntakeRevision] = []
    for row in records:
        payload = row.revision or {}
        record_data = payload.get("record")
        if not record_data:
            continue
        try:
            confirmed_at_raw = payload.get("confirmed_at")
            if isinstance(confirmed_at_raw, str):
                confirmed_at = datetime.fromisoformat(confirmed_at_raw)
            else:
                confirmed_at = _utcnow()

            revision = IntakeRevision(
                version=int(payload.get("version", len(revisions) + 1)),
                record=InterviewRecord.model_validate(record_data),
                confirmed_at=confirmed_at,
                confirmation_notes=list(payload.get("confirmation_notes", [])),
            )
            revisions.append(revision)
        except (ValidationError, ValueError) as exc:
            logger.warning("Failed to deserialize intake revision: %s", exc)
    store._revisions = revisions
    return store


def _revision_to_dict(revision: IntakeRevision) -> Dict[str, Any]:
    return revision.to_dict()


@dataclass
class _SessionEntry:
    session: "PersistentSession"
    last_access: datetime


class PersistentSession(SessionABC):
    """Session that mirrors its state to Supabase Postgres."""

    def __init__(
        self,
        session_id: str,
        owner_user_id: str,
        items: list[TResponseInputItem],
        timeline: TimelineState,
        intake_store: IntakeStore,
        planning_context: PlanningContext | None,
        optimization_result: OptimizationResult | None,
    ) -> None:
        self.session_id = session_id
        self._owner_user_id = owner_user_id
        self._items = items
        self._timeline = timeline
        self._intake = intake_store
        self._planning_context = planning_context
        self._optimization_result = optimization_result
        self._timeline_watchers: set[asyncio.Queue[TimelineUpdatePayload]] = set()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def load_or_create(
        cls, session_id: Optional[str], user_id: str
    ) -> Tuple[str, "PersistentSession"]:
        if not user_id:
            raise ValueError("user_id is required to create or load a session")
        with SessionLocal() as db:
            repo = SessionRepository(db)
            if session_id:
                record = repo.get_session(session_id)
                if record is not None and record.user_id != user_id:
                    raise PermissionError("Session does not belong to this user")
                if record is None:
                    repo.upsert_session(session_id, user_id)
            else:
                session_id = _generate_session_id()
                while repo.get_session(session_id) is not None:
                    session_id = _generate_session_id()
                repo.upsert_session(session_id, user_id)
            db.commit()

        session = cls._load(session_id)
        session.ensure_owner(user_id)
        return session_id, session

    @classmethod
    def load_existing(cls, session_id: str) -> Optional["PersistentSession"]:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            record = repo.get_session(session_id)
        if record is None:
            return None
        return cls._load(session_id)

    @classmethod
    def _load(cls, session_id: str) -> "PersistentSession":
        with SessionLocal() as db:
            repo = SessionRepository(db)
            record = repo.get_session(session_id)
            if record is None:
                raise ValueError(f"Session {session_id} not found in database")

            messages = [msg.content for msg in repo.list_messages(session_id)]
            timeline_dict = repo.get_timeline(session_id) or {}
            intake_store = _intake_store_from_records(
                repo.list_intake_revisions(session_id)
            )
            planning_dict = repo.get_planning_context(session_id)
            optimization_model = repo.get_optimization_result(session_id)

        planning_context = (
            PlanningContext.model_validate(planning_dict)
            if planning_dict is not None
            else None
        )

        optimization_result = (
            OptimizationResult.model_validate(optimization_model.result)
            if optimization_model is not None
            else None
        )
        if optimization_result is not None and optimization_model is not None:
            optimization_result.engine_recommended_index = (
                optimization_model.engine_recommended_index
            )
            optimization_result.advisor_recommended_index = (
                optimization_model.advisor_recommended_index
            )

        timeline_state = _timeline_from_dict(timeline_dict)

        message_items: list[TResponseInputItem] = [
            cast(TResponseInputItem, message) for message in messages
        ]

        return cls(
            session_id=session_id,
            owner_user_id=record.user_id,
            items=message_items,
            timeline=timeline_state,
            intake_store=intake_store,
            planning_context=planning_context,
            optimization_result=optimization_result,
        )

    # ------------------------------------------------------------------
    # Ownership helpers
    # ------------------------------------------------------------------

    @property
    def owner_user_id(self) -> str:
        with self._lock:
            return self._owner_user_id

    def ensure_owner(self, user_id: str) -> None:
        with self._lock:
            if self._owner_user_id != user_id:
                raise PermissionError("Session ownership mismatch")

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    async def get_items(self, limit: Optional[int] = None) -> list[TResponseInputItem]:
        with self._lock:
            if limit is None:
                snapshot: list[TResponseInputItem] = list(self._items)
            else:
                snapshot = self._items[-limit:]
        return cast(list[TResponseInputItem], copy.deepcopy(snapshot))

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        if not items:
            return
        payload = cast(list[TResponseInputItem], copy.deepcopy(items))
        with self._lock:
            self._items.extend(payload)
        await asyncio.get_running_loop().run_in_executor(
            None, self._append_messages, payload
        )

    async def pop_item(self) -> TResponseInputItem | None:
        with self._lock:
            item = self._items.pop() if self._items else None
        if item is not None:
            await asyncio.get_running_loop().run_in_executor(
                None, self._pop_last_message
            )
        return cast(TResponseInputItem | None, copy.deepcopy(item))

    async def clear_session(self) -> None:
        with self._lock:
            self._items.clear()
            self._timeline.clear()
            self._intake.clear()
            self._planning_context = None
            self._optimization_result = None
            watchers = list(self._timeline_watchers)
            payload = self._timeline.to_dict()
        await asyncio.get_running_loop().run_in_executor(None, self._clear_persistence)
        self._broadcast_timeline(payload, watchers)

    # ------------------------------------------------------------------
    # Timeline helpers
    # ------------------------------------------------------------------

    def get_timeline(self) -> TimelineState:
        with self._lock:
            return copy.deepcopy(self._timeline)

    async def apply_timeline_update(
        self, mutator: Callable[[TimelineState], None]
    ) -> TimelineState:
        with self._lock:
            updated = copy.deepcopy(self._timeline)
            mutator(updated)
            self._timeline = updated
            watchers = list(self._timeline_watchers)
            payload = updated.to_dict()
        await asyncio.get_running_loop().run_in_executor(
            None, self._persist_timeline, payload
        )
        self._broadcast_timeline(payload, watchers)
        return copy.deepcopy(updated)

    # ------------------------------------------------------------------
    # Intake helpers
    # ------------------------------------------------------------------

    def get_intake(self) -> IntakeStore:
        with self._lock:
            return copy.deepcopy(self._intake)

    def get_intake_record(self) -> Optional[InterviewRecord]:
        with self._lock:
            current = self._intake.current()
            if current is None:
                return None
            return current.record.model_copy(deep=True)

    def save_intake_submission(self, submission: IntakeSubmission) -> IntakeRevision:
        with self._lock:
            revision = self._intake.submit(submission)
        self._persist_intake_revision(_revision_to_dict(revision))
        return revision

    # ------------------------------------------------------------------
    # Planning / Optimization helpers
    # ------------------------------------------------------------------

    def set_planning_context(self, context: PlanningContext) -> PlanningContext:
        with self._lock:
            self._planning_context = context.model_copy(deep=True)
        self._persist_planning_context(self._planning_context)
        return self._planning_context.model_copy(deep=True)

    async def set_planning_context_async(
        self, context: PlanningContext
    ) -> PlanningContext:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.set_planning_context, context)

    def get_planning_context(self) -> PlanningContext | None:
        with self._lock:
            return (
                self._planning_context.model_copy(deep=True)
                if self._planning_context
                else None
            )

    def set_optimization_result(self, result: OptimizationResult) -> OptimizationResult:
        with self._lock:
            self._optimization_result = result.model_copy(deep=True)
        self._persist_optimization_result(self._optimization_result)
        return self._optimization_result.model_copy(deep=True)

    async def set_optimization_result_async(
        self, result: OptimizationResult
    ) -> OptimizationResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.set_optimization_result, result)

    def get_optimization_result(self) -> OptimizationResult | None:
        with self._lock:
            return (
                self._optimization_result.model_copy(deep=True)
                if self._optimization_result
                else None
            )

    # ------------------------------------------------------------------
    # Timeline watchers
    # ------------------------------------------------------------------

    def register_timeline_watcher(self) -> asyncio.Queue[TimelineUpdatePayload]:
        queue: asyncio.Queue[TimelineUpdatePayload] = asyncio.Queue()
        with self._lock:
            self._timeline_watchers.add(queue)
            payload = self._timeline.to_dict()
        queue.put_nowait(payload)
        return queue

    def unregister_timeline_watcher(
        self, queue: asyncio.Queue[TimelineUpdatePayload]
    ) -> None:
        with self._lock:
            self._timeline_watchers.discard(queue)

    def _broadcast_timeline(
        self,
        payload: TimelineUpdatePayload,
        watchers: Optional[list[asyncio.Queue[TimelineUpdatePayload]]] = None,
    ) -> None:
        targets = watchers if watchers is not None else list(self._timeline_watchers)
        for queue in targets:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(
                    "Timeline watcher queue full for session %s", self.session_id
                )

    # ------------------------------------------------------------------
    # Persistence helpers (run in executor or synchronously)
    # ------------------------------------------------------------------

    def _append_messages(self, items: list[TResponseInputItem]) -> None:
        dict_items: list[dict[str, Any]] = [
            cast(dict[str, Any], item) for item in items if isinstance(item, dict)
        ]
        if not dict_items:
            return
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.append_messages(self.session_id, dict_items)
            db.commit()

    def _pop_last_message(self) -> None:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.pop_last_message(self.session_id)
            db.commit()

    def _persist_timeline(self, state: dict[str, Any]) -> None:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.upsert_timeline(self.session_id, state)
            db.commit()

    def _persist_intake_revision(self, revision: dict[str, Any]) -> None:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.add_intake_revision(self.session_id, revision)
            db.commit()

    def _persist_planning_context(self, context: PlanningContext | None) -> None:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            if context is None:
                repo.delete_planning_context(self.session_id)
            else:
                repo.save_planning_context(self.session_id, context.model_dump())
            db.commit()

    def _persist_optimization_result(self, result: OptimizationResult | None) -> None:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            if result is None:
                repo.delete_optimization_result(self.session_id)
            else:
                repo.save_optimization_result(
                    self.session_id,
                    result.model_dump(),
                    result.engine_recommended_index,
                    result.advisor_recommended_index,
                )
            db.commit()

    def _clear_persistence(self) -> None:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.clear_messages(self.session_id)
            repo.delete_timeline(self.session_id)
            repo.clear_intake(self.session_id)
            repo.delete_planning_context(self.session_id)
            repo.delete_optimization_result(self.session_id)
            db.commit()


# ----------------------------------------------------------------------
# Global session cache helpers
# ----------------------------------------------------------------------

_session_cache: Dict[str, _SessionEntry] = {}


def _purge_expired_sessions(now: datetime) -> None:
    ttl_minutes = settings.session_ttl_minutes
    max_entries = settings.session_max_entries

    if ttl_minutes > 0:
        expiry_threshold = now - timedelta(minutes=ttl_minutes)
        expired_keys = [
            key
            for key, entry in _session_cache.items()
            if entry.last_access < expiry_threshold
        ]
        for key in expired_keys:
            logger.debug("Evicting expired session: %s", key)
            del _session_cache[key]

    if max_entries > 0 and len(_session_cache) > max_entries:
        surplus = len(_session_cache) - max_entries
        if surplus > 0:
            ordered = sorted(
                _session_cache.items(), key=lambda item: item[1].last_access
            )
            for key, _ in ordered[:surplus]:
                logger.debug("Evicting LRU session to maintain capacity: %s", key)
                del _session_cache[key]


def get_or_create_session(
    session_id: Optional[str], user_id: str
) -> Tuple[str, PersistentSession]:
    if not user_id:
        raise ValueError("user_id is required to create or load a session")
    with _cache_lock:
        now = _utcnow()
        _purge_expired_sessions(now)

        if session_id:
            entry = _session_cache.get(session_id)
            if entry is not None:
                entry.session.ensure_owner(user_id)
                entry.last_access = now
                return session_id, entry.session

    new_id, session = PersistentSession.load_or_create(session_id, user_id)
    with _cache_lock:
        _session_cache[new_id] = _SessionEntry(session=session, last_access=_utcnow())
        _purge_expired_sessions(_utcnow())
    return new_id, session


def get_session(
    session_id: str,
    user_id: str | None = None,
) -> PersistentSession | None:
    now = _utcnow()

    with _cache_lock:
        _purge_expired_sessions(now)
        entry = _session_cache.get(session_id)
        if entry is not None:
            if user_id:
                entry.session.ensure_owner(user_id)
            entry.last_access = now
            return entry.session

    session = PersistentSession.load_existing(session_id)
    if session is None:
        return None
    if user_id:
        session.ensure_owner(user_id)

    with _cache_lock:
        _session_cache[session_id] = _SessionEntry(session=session, last_access=now)
        _purge_expired_sessions(now)
    return session


def clear_all_sessions() -> None:
    with _cache_lock:
        _session_cache.clear()


__all__ = [
    "get_or_create_session",
    "get_session",
    "clear_all_sessions",
    "PersistentSession",
]
