"""Session management utilities."""

from __future__ import annotations

import copy
import logging
import threading
import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple

from agents.items import TResponseInputItem
from agents.memory.session import SessionABC

from ..config import settings

logger = logging.getLogger(__name__)


class InMemorySession(SessionABC):
    """Lightweight session that keeps history in memory only."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._items: list[TResponseInputItem] = []
        self._lock = threading.RLock()

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


__all__ = ["get_or_create_session", "InMemorySession"]
