"""Tool for listing uploaded documents for the active session."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents import function_tool
from agents.tool_context import ToolContext

from ...models.context import ChatRunContext
from ...services import session_manager

logger = logging.getLogger(__name__)


@function_tool
async def list_uploaded_documents(
    ctx: ToolContext[ChatRunContext],
) -> str:
    """Return metadata about documents associated with the session."""

    context = getattr(ctx, "context", None)
    if not isinstance(context, ChatRunContext):
        return "ERROR: list_uploaded_documents requires chat session context."

    session = session_manager.get_session(context.session_id)
    if session is None:
        logger.error(
            "Session %s not found while listing uploaded documents",
            context.session_id,
        )
        return f"ERROR: session {context.session_id} not found."

    summaries = session.document_summaries()
    payload: dict[str, Any] = {
        "documents": [summary.model_dump() for summary in summaries],
        "count": len(summaries),
    }
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["list_uploaded_documents"]
