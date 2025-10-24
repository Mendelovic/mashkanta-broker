"""Tool for running mortgage mix optimization."""

from __future__ import annotations

import json
import logging

from agents import function_tool
from agents.tool_context import ToolContext

from ...models.context import ChatRunContext
from ...services import session_manager
from ...services.mix_optimizer import optimize_mixes

logger = logging.getLogger(__name__)


@function_tool
async def run_mix_optimization(ctx: ToolContext[ChatRunContext]) -> str:
    """Generate mix candidates and store the optimization result."""

    context = getattr(ctx, "context", None)
    if not isinstance(context, ChatRunContext):
        return "ERROR: optimization tool requires chat session context."

    session = session_manager.get_session(context.session_id)
    if session is None:
        return f"ERROR: session {context.session_id} not found."

    intake_record = session.get_intake_record()
    if intake_record is None:
        return "ERROR: cannot optimize mixes before intake is submitted."

    planning_context = session.get_planning_context()
    if planning_context is None:
        return "ERROR: cannot optimize mixes before planning context is computed."

    result = optimize_mixes(intake_record, planning_context)
    await session.set_optimization_result_async(result)

    logger.info(
        "mix optimization completed",
        extra={
            "session_id": context.session_id,
            "recommended_index": result.recommended_index,
        },
    )

    return json.dumps(result.model_dump(), ensure_ascii=False)


__all__ = ["run_mix_optimization"]
