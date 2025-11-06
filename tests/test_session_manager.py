from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING, cast

import pytest

from app.config import settings
from app.db.session import SessionLocal
from app.services import session_manager
from app.services.session_repository import SessionRepository
from tests.async_utils import run_async
from app.models.documents import DocumentExtract, DocumentKeyValue

if TYPE_CHECKING:
    from agents.items import TResponseInputItem
else:  # pragma: no cover - satisfies runtime when package missing
    TResponseInputItem = Any  # type: ignore[assignment]


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


def test_reasoning_messages_retained_in_storage():
    session_id, session = session_manager.get_or_create_session(
        None, user_id="reasoning-user"
    )
    reasoning_item: dict[str, Any] = {
        "id": "rs_test",
        "type": "reasoning",
        "summary": [],
    }
    user_item: dict[str, Any] = {"role": "user", "content": "שלום"}

    run_async(
        session.add_items(
            [
                cast(TResponseInputItem, reasoning_item),
                cast(TResponseInputItem, user_item),
            ]
        )
    )

    stored_items = run_async(session.get_items())
    assert len(stored_items) == 2

    try:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            persisted = repo.list_messages(session_id)
            assert len(persisted) == 2
    finally:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()


def test_ephemeral_message_temporary():
    session_id, session = session_manager.get_or_create_session(
        None, user_id="ephemeral-user"
    )
    try:
        ephemeral_id = session.push_ephemeral_message("system", "hint for agent")
        items = run_async(session.get_items())
        assert any(
            isinstance(item, dict)
            and item.get("role") == "system"
            and item.get("content") == "hint for agent"
            for item in items
        )

        session.pop_ephemeral_message(ephemeral_id)
        items_after = run_async(session.get_items())
        assert all(
            not (
                isinstance(item, dict)
                and item.get("role") == "system"
                and item.get("content") == "hint for agent"
            )
            for item in items_after
        )
    finally:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()


def test_document_artifacts_persist_and_reload(tmp_path):
    session_id, session = session_manager.get_or_create_session(
        None, user_id="doc-user"
    )
    try:
        temp_path = tmp_path / "doc.pdf"
        temp_path.write_bytes(b"fake pdf content")

        document_id = "doc123"
        session.register_document_stub(
            document_id,
            display_name="תלוש_שכר.pdf",
            original_filename="תלוש_שכר.pdf",
            mime_type="application/pdf",
            document_type="payslip",
            temp_path=str(temp_path),
        )

        docs = session.list_documents()
        assert len(docs) == 1
        assert docs[0].document_type == "payslip"
        assert session.resolve_document_for_temp_path(str(temp_path)) is not None
        assert session.get_document_temp_path(document_id) == str(temp_path)

        extract = DocumentExtract(
            locale="he-IL",
            text_preview="שכר נטו 12,000 ₪",
            text_truncated=False,
            summary={"key_values": "- שכר נטו: 12,000 ₪", "tables": "לא נמצאו טבלאות"},
            key_value_pairs=[
                DocumentKeyValue(key="שכר נטו", value="12,000 ₪", confidence=0.92)
            ],
            tables=[],
            warnings=["lowConfidence"],
        )

        session.set_document_extract(document_id, extract)

        # Clear the in-memory cache to force reload from the database.
        session_manager.clear_all_sessions()
        reloaded = session_manager.get_session(session_id)
        assert reloaded is not None

        summaries = reloaded.document_summaries()
        assert len(summaries) == 1
        summary = summaries[0]
        assert summary.document_type == "payslip"
        assert summary.warnings == ["lowConfidence"]
        assert summary.text_preview == "שכר נטו 12,000 ₪"
        assert summary.key_value_pairs[0].value == "12,000 ₪"
    finally:
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()
