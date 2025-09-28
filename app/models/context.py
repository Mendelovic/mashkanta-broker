"""Context models passed to agent runs."""

from dataclasses import dataclass


@dataclass
class ChatRunContext:
    """Runtime context carrying the active session id."""

    session_id: str


__all__ = ["ChatRunContext"]
