import json
from typing import Callable, Iterator

import pytest
from agents.tool_context import ToolContext

from app.agents.tools.intake_tool import submit_intake_record
from app.agents.tools.planning_tool import compute_planning_context
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


def create_intake_context(session_id: str, payload: str) -> ToolContext[ChatRunContext]:
    return ToolContext(
        context=ChatRunContext(session_id=session_id),
        tool_name=submit_intake_record.name,
        tool_call_id="intake-tool-call",
        tool_arguments=payload,
    )


def create_planning_context(session_id: str) -> ToolContext[ChatRunContext]:
    return ToolContext(
        context=ChatRunContext(session_id=session_id),
        tool_name=compute_planning_context.name,
        tool_call_id="planning-tool-call",
        tool_arguments="{}",
    )


def test_compute_planning_context_requires_intake(
    session_factory: Callable[[str], None],
) -> None:
    session_id = "planning-no-intake"
    user_id = "test-user-planning-1"
    session_factory(session_id)
    session_manager.get_or_create_session(session_id, user_id=user_id)

    planning_ctx = create_planning_context(session_id)
    result = run_async(compute_planning_context.on_invoke_tool(planning_ctx, "{}"))
    assert result.startswith("ERROR: cannot compute planning context")


def test_compute_planning_context_success(
    session_factory: Callable[[str], None],
) -> None:
    session_id = "planning-success"
    user_id = "test-user-planning-2"
    session_factory(session_id)
    _, session = session_manager.get_or_create_session(session_id, user_id=user_id)
    submission = build_submission()
    intake_payload = json.dumps({"submission": submission.model_dump()})
    intake_ctx = create_intake_context(session_id, intake_payload)
    run_async(submit_intake_record.on_invoke_tool(intake_ctx, intake_payload))

    planning_ctx = create_planning_context(session_id)
    result = run_async(compute_planning_context.on_invoke_tool(planning_ctx, "{}"))
    data = json.loads(result)

    assert "weights" in data
    stored = session.get_planning_context()
    assert stored is not None
    assert stored.weights.payment_volatility == data["weights"]["payment_volatility"]
