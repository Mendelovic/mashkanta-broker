from __future__ import annotations

from typing import Callable, Iterator

import pytest

from app.services import session_manager
from app.services.session_queries import get_session_detail, list_user_sessions
from app.db.session import SessionLocal
from app.services.session_repository import SessionRepository
from tests.async_utils import run_async


@pytest.fixture(autouse=True)
def _clear_session_cache() -> Iterator[None]:
    session_manager.clear_all_sessions()
    try:
        yield
    finally:
        session_manager.clear_all_sessions()


@pytest.fixture
def session_cleanup() -> Iterator[Callable[[str], None]]:
    created: list[str] = []

    def _register(session_id: str) -> None:
        created.append(session_id)

    yield _register

    for session_id in created:
        session_manager._session_cache.pop(session_id, None)
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()


def _create_session(user_id: str, session_cleanup: Callable[[str], None]) -> str:
    session_id, _ = session_manager.get_or_create_session(None, user_id=user_id)
    session_cleanup(session_id)
    return session_id


def test_list_user_sessions_returns_summary(
    session_cleanup: Callable[[str], None],
) -> None:
    user_id = "list-user"
    session_id, session = session_manager.get_or_create_session(None, user_id=user_id)
    session_cleanup(session_id)

    run_async(session.add_items([{"role": "user", "content": "hello there"}]))

    summaries = list_user_sessions(user_id)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.session_id == session_id
    assert summary.message_count == 1
    assert summary.latest_message is not None
    assert summary.latest_message.role == "user"
    assert summary.latest_message.content.get("content") == "hello there"


def test_list_user_sessions_honors_limit(
    session_cleanup: Callable[[str], None],
) -> None:
    user_id = "limit-user"
    _create_session(user_id, session_cleanup)
    second_id = _create_session(user_id, session_cleanup)

    summaries_all = list_user_sessions(user_id)
    assert len(summaries_all) == 2
    assert summaries_all[0].session_id == second_id

    summaries_limited = list_user_sessions(user_id, limit=1)
    assert len(summaries_limited) == 1
    assert summaries_limited[0].session_id == second_id


def test_get_session_detail_returns_history(
    session_cleanup: Callable[[str], None],
) -> None:
    user_id = "detail-user"
    session_id, session = session_manager.get_or_create_session(None, user_id=user_id)
    session_cleanup(session_id)

    run_async(session.add_items([{"role": "user", "content": "hello detail"}]))

    detail = get_session_detail(session_id, user_id)
    assert detail is not None
    assert detail.session_id == session_id
    assert len(detail.messages) == 1
    assert detail.messages[0].role == "user"
    assert detail.messages[0].content.get("content") == "hello detail"
    assert isinstance(detail.timeline, dict)
    assert isinstance(detail.intake, dict)


def test_get_session_detail_rejects_other_user(
    session_cleanup: Callable[[str], None],
) -> None:
    user_id = "owner-user"
    session_id = _create_session(user_id, session_cleanup)

    detail = get_session_detail(session_id, "intruder-user")
    assert detail is None


def test_reasoning_entries_hidden_from_api(
    session_cleanup: Callable[[str], None],
) -> None:
    user_id = "reasoning-api-user"
    session_id, session = session_manager.get_or_create_session(None, user_id=user_id)
    session_cleanup(session_id)

    items = [
        {"role": "user", "content": "hi"},
        {"id": "rs_test", "type": "reasoning", "summary": []},
        {"role": "assistant", "content": "שלום"},
    ]
    run_async(session.add_items(items))

    summaries = list_user_sessions(user_id)
    assert summaries[0].message_count == 2
    assert summaries[0].latest_message is not None
    assert summaries[0].latest_message.role == "assistant"

    detail = get_session_detail(session_id, user_id)
    assert detail is not None
    assert len(detail.messages) == 2
    roles = [msg.role for msg in detail.messages]
    assert roles == ["user", "assistant"]

    with SessionLocal() as db:
        repo = SessionRepository(db)
        persisted = repo.list_messages(session_id)
        assert len(persisted) == 3
