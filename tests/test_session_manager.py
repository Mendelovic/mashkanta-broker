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

    session_id, _ = session_manager.get_or_create_session(None, user_id="test-user-ttl")
    cached_entry = session_manager._session_cache.get(session_id)
    assert cached_entry is not None

    # Force the entry to look stale and trigger purge on next access.
    session_manager._session_cache[session_id].last_access = datetime.now() - timedelta(
        minutes=2
    )

    session_manager.get_or_create_session(None, user_id="test-user-ttl-2")
    assert session_id not in session_manager._session_cache

    # Accessing the session again should reload it into the cache.
    reloaded = session_manager.get_session(session_id)
    assert reloaded is not None
    assert session_id in session_manager._session_cache


def test_session_cache_respects_capacity():
    settings.session_max_entries = 2
    ids = []
    for idx in range(3):
        session_id, _ = session_manager.get_or_create_session(
            None, user_id=f"test-user-{idx}"
        )
        ids.append(session_id)

    assert len(session_manager._session_cache) == settings.session_max_entries
    assert ids[0] not in session_manager._session_cache


def test_get_session_enforces_owner():
    session_id, _ = session_manager.get_or_create_session(None, user_id="owner-user")

    with pytest.raises(PermissionError):
        session_manager.get_session(session_id, user_id="intruder")


def test_get_session_purges_expired_entries():
    settings.session_ttl_minutes = 1
    session_id, _ = session_manager.get_or_create_session(None, user_id="ttl-user")

    # Stale the cache entry and ensure the read path purges it before reload.
    session_manager._session_cache[session_id].last_access = datetime.now() - timedelta(
        minutes=2
    )

    reloaded = session_manager.get_session(session_id)
    assert reloaded is not None
    assert session_id in session_manager._session_cache
