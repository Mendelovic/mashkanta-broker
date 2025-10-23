"""Timeline snapshot and streaming endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..services.session_manager import get_session
from ..security import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/sessions", tags=["timeline"])


@router.get("/{session_id}/timeline")
async def timeline_snapshot(
    session_id: str, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict:
    session = get_session(session_id, user_id=current_user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get_timeline()
    return state.to_dict()


@router.get("/{session_id}/timeline/stream")
async def timeline_stream(
    session_id: str, current_user: AuthenticatedUser = Depends(get_current_user)
) -> StreamingResponse:
    session = get_session(session_id, user_id=current_user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    queue = session.register_timeline_watcher()

    async def event_source() -> AsyncGenerator[str, None]:
        try:
            while True:
                payload = await queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            session.unregister_timeline_watcher(queue)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }

    return StreamingResponse(
        event_source(), media_type="text/event-stream", headers=headers
    )


__all__ = ["router"]
