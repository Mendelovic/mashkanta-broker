import json
from typing import Callable, Iterator

import pytest
from agents.tool_context import ToolContext

from app.agents.tools.intake_tool import submit_intake_record
from app.models.context import ChatRunContext
from app.services import session_manager
from app.db.session import SessionLocal
from app.services.session_repository import SessionRepository

from .factories import build_submission
from .async_utils import run_async


@pytest.fixture
def cleanup_session() -> Iterator[Callable[[str], None]]:
    created_ids: list[str] = []

    def _register(session_id: str) -> None:
        created_ids.append(session_id)
        session_manager._session_cache.pop(session_id, None)
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()

    yield _register

    for session_id in created_ids:
        session_manager._session_cache.pop(session_id, None)
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()


def create_tool_context(session_id: str, payload: str) -> ToolContext[ChatRunContext]:
    return ToolContext(
        context=ChatRunContext(session_id=session_id),
        tool_name=submit_intake_record.name,
        tool_call_id="tool-call-test",
        tool_arguments=payload,
    )


def test_submit_intake_record_persists_revision(
    cleanup_session: Callable[[str], None],
) -> None:
    session_id = "test-intake-session"
    user_id = "test-user-intake"
    cleanup_session(session_id)
    session_manager._session_cache.pop(session_id, None)

    _, session = session_manager.get_or_create_session(session_id, user_id=user_id)
    submission = build_submission()
    arguments = json.dumps({"submission": submission.model_dump()})
    tool_ctx = create_tool_context(session_id, arguments)

    result_json = run_async(submit_intake_record.on_invoke_tool(tool_ctx, arguments))
    result = json.loads(result_json)

    assert result["version"] == 1
    assert result["record"]["loan"]["term_years"] == submission.record.loan.term_years

    stored_record = session.get_intake_record()
    assert stored_record is not None
    assert stored_record.model_dump() == submission.record.model_dump()

    store = session.get_intake()
    assert store.current() is not None
    assert len(store.revisions()) == 1


def test_submit_intake_record_requires_existing_session() -> None:
    session_id = "missing-session"
    submission = build_submission()
    arguments = json.dumps({"submission": submission.model_dump()})
    tool_ctx = create_tool_context(session_id, arguments)

    result = run_async(submit_intake_record.on_invoke_tool(tool_ctx, arguments))
    assert result.startswith("ERROR: session missing-session not found.")
