import json
from typing import Callable, Iterator

import pytest
from agents.tool_context import ToolContext

from app.agents.tools.intake_tool import submit_intake_record
from app.agents.tools.planning_tool import compute_planning_context
from app.agents.tools.optimization_tool import run_mix_optimization
from app.models.context import ChatRunContext
from app.services import session_manager
from app.db.session import SessionLocal
from app.services.session_repository import SessionRepository
from tests.factories import build_submission
from tests.async_utils import run_async


@pytest.fixture
def session_factory() -> Iterator[Callable[[str], None]]:
    created: list[str] = []

    def _prepare(session_id: str) -> None:
        session_manager._session_cache.pop(session_id, None)
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()
        created.append(session_id)

    yield _prepare

    for session_id in created:
        session_manager._session_cache.pop(session_id, None)
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()


def create_context(
    session_id: str, tool_name: str, payload: str = "{}"
) -> ToolContext[ChatRunContext]:
    return ToolContext(
        context=ChatRunContext(session_id=session_id),
        tool_name=tool_name,
        tool_call_id=f"{tool_name}-call",
        tool_arguments=payload,
    )


def test_run_mix_optimization_requires_planning(
    session_factory: Callable[[str], None],
) -> None:
    session_id = "opt-no-planning"
    user_id = "test-user-opt-1"
    session_factory(session_id)
    _, session = session_manager.get_or_create_session(session_id, user_id=user_id)
    submission = build_submission()
    intake_payload = json.dumps({"submission": submission.model_dump()})
    intake_ctx = create_context(session_id, submit_intake_record.name, intake_payload)
    run_async(submit_intake_record.on_invoke_tool(intake_ctx, intake_payload))

    ctx = create_context(session_id, run_mix_optimization.name)
    result = run_async(run_mix_optimization.on_invoke_tool(ctx, "{}"))
    assert result.startswith("ERROR: cannot optimize mixes")


def test_run_mix_optimization_success(session_factory: Callable[[str], None]) -> None:
    session_id = "opt-success"
    user_id = "test-user-opt-2"
    session_factory(session_id)
    _, session = session_manager.get_or_create_session(session_id, user_id=user_id)
    submission = build_submission()
    intake_payload = json.dumps({"submission": submission.model_dump()})
    intake_ctx = create_context(session_id, submit_intake_record.name, intake_payload)
    run_async(submit_intake_record.on_invoke_tool(intake_ctx, intake_payload))

    planning_ctx = create_context(session_id, compute_planning_context.name)
    run_async(compute_planning_context.on_invoke_tool(planning_ctx, "{}"))

    opt_ctx = create_context(session_id, run_mix_optimization.name)
    result_json = run_async(run_mix_optimization.on_invoke_tool(opt_ctx, "{}"))
    data = json.loads(result_json)

    assert "candidates" in data
    assert data.get("engine_recommended_index") is not None
    assert data.get("advisor_recommended_index") is not None
    assert data.get("term_sweep")
    assert data.get("term_sweep")
    stored = session.get_optimization_result()
    assert stored is not None
    assert len(stored.candidates) == len(data["candidates"])
    assert stored.engine_recommended_index is not None
    assert stored.advisor_recommended_index is not None
    assert stored.term_sweep
    assert "pareto_alerts" in stored.assumptions
    assert stored.assumptions["pareto_alerts"] == []
