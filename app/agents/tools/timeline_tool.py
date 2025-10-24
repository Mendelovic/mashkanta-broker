"""Timeline event tool for the mortgage broker agent."""

from __future__ import annotations

import logging
import uuid
from typing import Optional, TypedDict

from agents import function_tool
from agents.tool_context import ToolContext

from ...models.context import ChatRunContext
from ...models.timeline import (
    TimelineDetail,
    TimelineEvent,
    TimelineEventStatus,
    TimelineEventType,
    TimelineStage,
    TimelineState,
)
from ...services.session_manager import get_session

logger = logging.getLogger(__name__)


class TimelineDetailInput(TypedDict, total=False):
    """Key/value pair accepted by the timeline event tool."""

    label: str
    value: str


@function_tool
async def record_timeline_event(
    ctx: ToolContext[ChatRunContext],
    *,
    title: str,
    stage: str,
    event_type: str,
    status: str = TimelineEventStatus.ACTIVE.value,
    description: Optional[str] = None,
    bank_name: Optional[str] = None,
    details: Optional[list[TimelineDetailInput]] = None,
    event_id: Optional[str] = None,
) -> str:
    """Create or update a timeline event for the active chat session."""

    context = getattr(ctx, "context", None)
    if not isinstance(context, ChatRunContext):
        return "ERROR: timeline context unavailable for this tool call."

    session = get_session(context.session_id)
    if session is None:
        return f"ERROR: session {context.session_id} not found."

    try:
        stage_enum = TimelineStage(stage)
    except ValueError:
        valid = ", ".join(stage.value for stage in TimelineStage)
        return f"ERROR: unknown stage '{stage}'. Expected one of: {valid}."

    try:
        type_enum = TimelineEventType(event_type)
    except ValueError:
        valid = ", ".join(t.value for t in TimelineEventType)
        return f"ERROR: unknown event_type '{event_type}'. Expected one of: {valid}."

    try:
        status_enum = TimelineEventStatus(status)
    except ValueError:
        valid = ", ".join(s.value for s in TimelineEventStatus)
        return f"ERROR: unknown status '{status}'. Expected one of: {valid}."

    detail_items: list[TimelineDetail] = []
    if details:
        for entry in details:
            label = str(entry.get("label", "")).strip()
            value = str(entry.get("value", "")).strip()
            if not label and not value:
                continue
            detail_items.append(
                TimelineDetail(label=label or "detail", value=value or "")
            )

    new_event = TimelineEvent(
        id=event_id or uuid.uuid4().hex,
        type=type_enum,
        title=title,
        stage=stage_enum,
        status=status_enum,
        description=description,
        bank_name=bank_name,
        details=detail_items,
    )

    def _apply_timeline(state: TimelineState) -> None:
        state.upsert_event(new_event)

    state = await session.apply_timeline_update(_apply_timeline)

    logger.info(
        "timeline event recorded",
        extra={"session_id": context.session_id, "event_id": new_event.id},
    )

    return (
        f"Timeline updated: event={new_event.id}, stage={new_event.stage.value}, "
        f"status={new_event.status.value}, version={state.version}"
    )


__all__ = [
    "record_timeline_event",
    "TimelineDetailInput",
]
