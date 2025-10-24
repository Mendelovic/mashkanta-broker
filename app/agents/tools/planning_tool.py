"""Tool for generating planning context from intake data."""

from __future__ import annotations

import json
import logging

from agents import function_tool
from agents.tool_context import ToolContext

from ...domain.schemas import IntakeSubmission
from ...models.context import ChatRunContext
from ...services import session_manager
from ...services.planning_mapper import build_planning_context

logger = logging.getLogger(__name__)


@function_tool
async def compute_planning_context(ctx: ToolContext[ChatRunContext]) -> str:
    """Generate and store the planning context using the latest confirmed intake."""

    context = getattr(ctx, "context", None)
    if not isinstance(context, ChatRunContext):
        return "ERROR: planning context requires chat session context."

    session = session_manager.get_session(context.session_id)
    if session is None:
        return f"ERROR: session {context.session_id} not found."

    intake_store = session.get_intake()
    revision = intake_store.current()
    if revision is None:
        return "ERROR: cannot compute planning context before intake is submitted."

    submission = IntakeSubmission(
        record=revision.record,
        confirmation_notes=revision.confirmation_notes,
    )
    planning_context = build_planning_context(submission)
    await session.set_planning_context_async(planning_context)

    logger.info(
        "planning context computed",
        extra={
            "session_id": context.session_id,
            "horizon": len(planning_context.income_timeline),
        },
    )

    return json.dumps(planning_context.model_dump(), ensure_ascii=False)


__all__ = ["compute_planning_context"]
