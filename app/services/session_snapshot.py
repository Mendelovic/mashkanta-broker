"""Session snapshot helpers for chat responses."""

from __future__ import annotations

from typing import Any, Optional, Tuple


def gather_session_state(
    session,
) -> Tuple[dict, dict, Optional[dict], Optional[Any], Optional[dict]]:
    timeline_state = session.get_timeline().to_dict()
    intake_state = session.get_intake().to_dict()
    planning_context = session.get_planning_context()
    planning_state = (
        planning_context.model_dump() if planning_context is not None else None
    )
    optimization_result = session.get_optimization_result()
    optimization_state = (
        optimization_result.model_dump() if optimization_result is not None else None
    )
    return (
        timeline_state,
        intake_state,
        planning_state,
        optimization_result,
        optimization_state,
    )


__all__ = ["gather_session_state"]
