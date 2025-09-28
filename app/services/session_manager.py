"""Session management utilities."""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from agents.items import TResponseInputItem
from agents.memory.session import SessionABC

from ..config import settings
from ..models.timeline import TimelineState

logger = logging.getLogger(__name__)

TimelineUpdatePayload = Dict[str, Any]


class InMemorySession(SessionABC):
    """In-memory session holding conversation history and timeline state."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._items: list[TResponseInputItem] = []
        self._lock = threading.RLock()
        self._timeline = TimelineState()
        self._timeline_watchers: set[asyncio.Queue[TimelineUpdatePayload]] = set()

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
_session_cache: Dict[str, InMemorySession] = {}


def _generate_session_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_part = uuid.uuid4().hex[:8]
    return f"{settings.default_session_prefix}{timestamp}_{unique_part}"


def get_or_create_session(session_id: Optional[str]) -> Tuple[str, InMemorySession]:
    """Return an existing in-memory session or create a new one."""

    if session_id and session_id in _session_cache:
        return session_id, _session_cache[session_id]

    new_id = session_id or _generate_session_id()
    session = InMemorySession(new_id)
    _session_cache[new_id] = session
    logger.debug("Created new session: %s", new_id)
    return new_id, session


def get_session(session_id: str) -> InMemorySession | None:
    """Return a session when it already exists."""

    return _session_cache.get(session_id)


__all__ = ["get_or_create_session", "get_session", "InMemorySession"]
