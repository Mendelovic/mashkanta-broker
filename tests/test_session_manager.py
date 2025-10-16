from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.services import session_manager


@pytest.fixture(autouse=True)
def _reset_sessions():
    original_max = settings.session_max_entries
    original_ttl = settings.session_ttl_minutes
    session_manager.clear_all_sessions()
    try:
        yield
    finally:
        settings.session_max_entries = original_max
        settings.session_ttl_minutes = original_ttl
        session_manager.clear_all_sessions()


def test_sessions_expire_after_ttl():
    settings.session_ttl_minutes = 1

    session_id, _ = session_manager.get_or_create_session(None)
    assert session_manager.get_session(session_id) is not None

    # Force the entry to look stale and trigger purge on next access.
    session_manager._session_cache[session_id].last_access = datetime.now() - timedelta(
        minutes=2
    )

    session_manager.get_or_create_session(None)
    assert session_manager.get_session(session_id) is None


def test_session_cache_respects_capacity():
    settings.session_max_entries = 2
    ids = []
    for _ in range(3):
        session_id, _ = session_manager.get_or_create_session(None)
        ids.append(session_id)

    assert len(session_manager._session_cache) == 2
    assert ids[0] not in session_manager._session_cache
