"""Endpoints for enumerating and loading user chat sessions."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.session import SessionDetail, SessionSummary
from ..security import AuthenticatedUser, get_current_user
from ..services.session_queries import get_session_detail, list_user_sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionSummary])
def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[SessionSummary]:
    return list_user_sessions(current_user.user_id, limit=limit)


@router.get("/{session_id}", response_model=SessionDetail)
async def read_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> SessionDetail:
    detail = get_session_detail(session_id, current_user.user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


__all__ = ["router"]
