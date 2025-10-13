"""Tools for submitting validated intake records."""

from __future__ import annotations

import json
import logging

from agents import function_tool
from agents.tool_context import ToolContext
from pydantic import ValidationError

from ...domain.schemas import IntakeSubmission
from ...models.context import ChatRunContext
from ...services.session_manager import get_session

logger = logging.getLogger(__name__)


@function_tool
def submit_intake_record(
    ctx: ToolContext[ChatRunContext],
    submission: IntakeSubmission,
) -> str:
    """
    Persist a fully validated intake submission for the active conversation session.

    The `submission` payload must conform to the IntakeSubmission schema, ensuring
    all mandatory regulatory data (borrower, property, loan, preferences) is present.
    """

    context = getattr(ctx, "context", None)
    if not isinstance(context, ChatRunContext):
        return "ERROR: intake tool requires chat session context."

    session = get_session(context.session_id)
    if session is None:
        return f"ERROR: session {context.session_id} not found."

    try:
        revision = session.save_intake_submission(submission)
    except ValidationError as exc:
        logger.warning("intake submission validation failed: %s", exc)
        return f"ERROR: intake submission invalid - {exc}"

    logger.info(
        "intake submission recorded",
        extra={
            "session_id": context.session_id,
            "version": revision.version,
            "has_summary": bool(revision.record.interview_summary),
        },
    )

    payload = revision.to_dict()
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["submit_intake_record"]
