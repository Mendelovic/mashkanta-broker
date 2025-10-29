"""Query helpers for listing and loading session history for API responses."""

from __future__ import annotations

from typing import List, Optional

from ..db import SessionLocal
from ..models.session import SessionDetail, SessionMessageModel, SessionSummary
from .chat_payload import build_optimization_payload
from .session_manager import get_session
from .session_repository import SessionRepository
from .session_snapshot import gather_session_state


def list_user_sessions(user_id: str, limit: Optional[int] = None) -> List[SessionSummary]:
    """Return session summaries for a given user ordered by most recent update."""

    with SessionLocal() as db:
        repo = SessionRepository(db)
        records = repo.list_sessions_for_user(user_id, limit=limit)

        summaries: List[SessionSummary] = []
        for record in records:
            latest_message_row = repo.get_latest_message(record.session_id)
            message_count = repo.count_messages(record.session_id)

            latest_message = (
                SessionMessageModel(
                    id=latest_message_row.id,
                    role=latest_message_row.role,
                    content=latest_message_row.content
                    if isinstance(latest_message_row.content, dict)
                    else {"value": latest_message_row.content},
                    created_at=latest_message_row.created_at,
                )
                if latest_message_row is not None
                else None
            )

            summaries.append(
                SessionSummary(
                    session_id=record.session_id,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    message_count=message_count,
                    latest_message=latest_message,
                )
            )

    return summaries


def get_session_detail(session_id: str, user_id: str) -> SessionDetail | None:
    """Load the complete session history for a user-owned session."""

    with SessionLocal() as db:
        repo = SessionRepository(db)
        record = repo.get_session(session_id, user_id=user_id)
        if record is None:
            return None
        message_rows = repo.list_messages(session_id)

    session = get_session(session_id, user_id=user_id)
    if session is None:
        return None

    (
        timeline_state,
        intake_state,
        planning_state,
        optimization_result,
        optimization_state,
    ) = gather_session_state(session)

    (
        optimization_candidates,
        optimization_matrix,
        optimization_summary,
        term_sweep_rows,
        engine_recommended_index,
        advisor_recommended_index,
    ) = build_optimization_payload(optimization_result)

    messages = [
        SessionMessageModel(
            id=row.id,
            role=row.role,
            content=row.content
            if isinstance(row.content, dict)
            else {"value": row.content},
            created_at=row.created_at,
        )
        for row in message_rows
    ]

    return SessionDetail(
        session_id=record.session_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        messages=messages,
        timeline=timeline_state or {},
        intake=intake_state or {},
        planning=planning_state,
        optimization=optimization_state,
        optimization_summary=optimization_summary,
        optimization_candidates=optimization_candidates or None,
        optimization_matrix=optimization_matrix or None,
        engine_recommended_index=engine_recommended_index,
        advisor_recommended_index=advisor_recommended_index,
        term_sweep=term_sweep_rows or None,
    )


__all__ = ["list_user_sessions", "get_session_detail"]
