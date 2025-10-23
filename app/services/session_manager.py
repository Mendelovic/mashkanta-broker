"""Session management utilities."""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
import uuid
from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from agents.items import TResponseInputItem
from agents.memory.session import SessionABC

from ..config import settings
from ..domain.schemas import (
    IntakeSubmission,
    InterviewRecord,
    PlanningContext,
    OptimizationResult,
)
from ..models.timeline import TimelineState
from ..models.intake import IntakeRevision, IntakeStore

logger = logging.getLogger(__name__)

TimelineUpdatePayload = Dict[str, Any]
_cache_lock = threading.RLock()


def _utcnow() -> datetime:
    return datetime.now()


@dataclass
class _SessionEntry:
    session: "InMemorySession"
    last_access: datetime


class InMemorySession(SessionABC):
    """In-memory session holding conversation history and timeline state."""

    def __init__(self, session_id: str, owner_user_id: str | None = None) -> None:
        self.session_id = session_id
        self._items: list[TResponseInputItem] = []
        self._lock = threading.RLock()
        self._timeline = TimelineState()
        self._intake = IntakeStore()
        self._planning_context: PlanningContext | None = None
        self._optimization_result: OptimizationResult | None = None
        self._timeline_watchers: set[asyncio.Queue[TimelineUpdatePayload]] = set()
        self._owner_user_id = owner_user_id

    @property
    def owner_user_id(self) -> str | None:
        with self._lock:
            return self._owner_user_id

    def ensure_owner(self, user_id: str) -> None:
        with self._lock:
            if self._owner_user_id is None:
                self._owner_user_id = user_id

    async def get_items(self, limit: Optional[int] = None) -> list[TResponseInputItem]:
        with self._lock:
            if limit is None:
                snapshot = list(self._items)
            else:
                snapshot = self._items[-limit:]
        return copy.deepcopy(snapshot)

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        if not items:
            return
        with self._lock:
            self._items.extend(copy.deepcopy(items))

    async def pop_item(self) -> TResponseInputItem | None:
        with self._lock:
            if not self._items:
                return None
            return copy.deepcopy(self._items.pop())

    async def clear_session(self) -> None:
        with self._lock:
            self._items.clear()
            self._timeline.clear()
            self._intake.clear()
            self._planning_context = None
            self._optimization_result = None
            watchers = list(self._timeline_watchers)
            payload = self._timeline.to_dict()
        self._broadcast_timeline(payload, watchers)

    # ------------------------------------------------------------------
    # Timeline helpers
    # ------------------------------------------------------------------

    def get_timeline(self) -> TimelineState:
        with self._lock:
            return copy.deepcopy(self._timeline)

    def apply_timeline_update(
        self, mutator: Callable[[TimelineState], None]
    ) -> TimelineState:
        with self._lock:
            updated = copy.deepcopy(self._timeline)
            mutator(updated)
            self._timeline = updated
            watchers = list(self._timeline_watchers)
            payload = updated.to_dict()
        self._broadcast_timeline(payload, watchers)
        return copy.deepcopy(updated)

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
            self._planning_context = None
            self._optimization_result = None
        return revision

    def set_planning_context(self, context: PlanningContext) -> PlanningContext:
        with self._lock:
            self._planning_context = context.model_copy(deep=True)
            self._optimization_result = None
            return self._planning_context.model_copy(deep=True)

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
            return self._optimization_result.model_copy(deep=True)

    def get_optimization_result(self) -> OptimizationResult | None:
        with self._lock:
            return (
                self._optimization_result.model_copy(deep=True)
                if self._optimization_result
                else None
            )

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


# TODO: Add session eviction or persistence before production use to avoid unbounded growth.
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


def _generate_session_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_part = uuid.uuid4().hex[:8]
    return f"{settings.default_session_prefix}{timestamp}_{unique_part}"


def get_or_create_session(
    session_id: Optional[str], user_id: str | None = None
) -> Tuple[str, InMemorySession]:
    """Return an existing in-memory session for a user or create a new one."""

    with _cache_lock:
        now = _utcnow()
        _purge_expired_sessions(now)

        if session_id:
            entry = _session_cache.get(session_id)
            if entry is not None:
                if user_id:
                    owner = entry.session.owner_user_id
                    if owner is not None and owner != user_id:
                        raise PermissionError("Session does not belong to this user")
                    entry.session.ensure_owner(user_id)
                entry.last_access = now
                return session_id, entry.session

        new_id = session_id or _generate_session_id()
        while new_id in _session_cache:
            new_id = _generate_session_id()

        session = InMemorySession(new_id, owner_user_id=user_id)
        _session_cache[new_id] = _SessionEntry(session=session, last_access=now)
        logger.debug("Created new session: %s", new_id)
        _purge_expired_sessions(now)
        return new_id, session


def get_session(session_id: str, user_id: str | None = None) -> InMemorySession | None:
    """Return a session when it already exists."""

    with _cache_lock:
        entry = _session_cache.get(session_id)
        if entry is None:
            return None
        if user_id:
            owner = entry.session.owner_user_id
            if owner is not None and owner != user_id:
                return None
            entry.session.ensure_owner(user_id)
        entry.last_access = _utcnow()
        return entry.session


def clear_all_sessions() -> None:
    """Clear all cached sessions (primarily for testing and maintenance)."""

    with _cache_lock:
        _session_cache.clear()


__all__ = [
    "get_or_create_session",
    "get_session",
    "InMemorySession",
    "clear_all_sessions",
]
