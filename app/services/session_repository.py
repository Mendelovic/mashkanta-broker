"""Database repository for persistent chat sessions."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy import delete, select, update, func
from sqlalchemy.orm import Session

from ..db import models


class SessionRepository:
    """CRUD helpers around the persistent session schema."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert_session(self, session_id: str, user_id: str) -> models.UserSession:
        record = self._db.get(models.UserSession, session_id)
        if record:
            if record.user_id != user_id:
                raise PermissionError("Session owned by another user")
            self._db.execute(
                update(models.UserSession)
                .where(models.UserSession.session_id == session_id)
                .values(updated_at=func.now())
            )
            self._db.flush()
            self._db.refresh(record)
            return record

        record = models.UserSession(session_id=session_id, user_id=user_id)
        self._db.add(record)
        self._db.flush()
        return record

    def get_session(
        self, session_id: str, user_id: Optional[str] = None
    ) -> Optional[models.UserSession]:
        stmt = select(models.UserSession).where(
            models.UserSession.session_id == session_id
        )
        if user_id is not None:
            stmt = stmt.where(models.UserSession.user_id == user_id)
        result = self._db.execute(stmt)
        return result.scalar_one_or_none()

    def append_messages(self, session_id: str, items: Iterable[dict[str, Any]]) -> None:
        records = []
        for item in items:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "unknown"))
            records.append(
                models.SessionMessage(session_id=session_id, role=role, content=item)
            )
        if records:
            self._db.add_all(records)
            self._db.flush()

    def list_messages(self, session_id: str) -> list[models.SessionMessage]:
        stmt = (
            select(models.SessionMessage)
            .where(models.SessionMessage.session_id == session_id)
            .order_by(models.SessionMessage.created_at, models.SessionMessage.id)
        )
        result = self._db.execute(stmt)
        return list(result.scalars())

    def count_messages(self, session_id: str) -> int:
        stmt = (
            select(func.count(models.SessionMessage.id))
            .where(models.SessionMessage.session_id == session_id)
            .select_from(models.SessionMessage)
        )
        return int(self._db.execute(stmt).scalar_one())

    def get_latest_message(
        self, session_id: str
    ) -> Optional[models.SessionMessage]:
        stmt = (
            select(models.SessionMessage)
            .where(models.SessionMessage.session_id == session_id)
            .order_by(models.SessionMessage.created_at.desc(), models.SessionMessage.id.desc())
            .limit(1)
        )
        result = self._db.execute(stmt)
        return result.scalar_one_or_none()

    def pop_last_message(self, session_id: str) -> Optional[models.SessionMessage]:
        stmt = (
            select(models.SessionMessage)
            .where(models.SessionMessage.session_id == session_id)
            .order_by(models.SessionMessage.id.desc())
            .limit(1)
        )
        result = self._db.execute(stmt)
        latest = result.scalar_one_or_none()
        if latest is None:
            return None
        self._db.delete(latest)
        self._db.flush()
        return latest

    def clear_messages(self, session_id: str) -> None:
        self._db.execute(
            delete(models.SessionMessage).where(
                models.SessionMessage.session_id == session_id
            )
        )
        self._db.flush()

    def delete_timeline(self, session_id: str) -> None:
        self._db.execute(
            delete(models.SessionTimelineSnapshot).where(
                models.SessionTimelineSnapshot.session_id == session_id
            )
        )
        self._db.flush()

    def upsert_timeline(self, session_id: str, state: dict[str, Any]) -> None:
        self._db.merge(
            models.SessionTimelineSnapshot(session_id=session_id, state=state)
        )
        self._db.flush()

    def get_timeline(self, session_id: str) -> Optional[dict[str, Any]]:
        snapshot = self._db.get(models.SessionTimelineSnapshot, session_id)
        return None if snapshot is None else snapshot.state

    def add_intake_revision(self, session_id: str, revision: dict[str, Any]) -> None:
        self._db.execute(
            update(models.SessionIntakeRevision)
            .where(
                models.SessionIntakeRevision.session_id == session_id,
                models.SessionIntakeRevision.is_latest.is_(True),
            )
            .values(is_latest=False)
        )
        self._db.add(
            models.SessionIntakeRevision(
                session_id=session_id, revision=revision, is_latest=True
            )
        )
        self._db.flush()

    def clear_intake(self, session_id: str) -> None:
        self._db.execute(
            delete(models.SessionIntakeRevision).where(
                models.SessionIntakeRevision.session_id == session_id
            )
        )
        self._db.flush()

    def latest_intake_revision(
        self, session_id: str
    ) -> Optional[models.SessionIntakeRevision]:
        stmt = (
            select(models.SessionIntakeRevision)
            .where(
                models.SessionIntakeRevision.session_id == session_id,
                models.SessionIntakeRevision.is_latest.is_(True),
            )
            .order_by(models.SessionIntakeRevision.created_at.desc())
            .limit(1)
        )
        result = self._db.execute(stmt)
        return result.scalar_one_or_none()

    def list_intake_revisions(
        self, session_id: str
    ) -> list[models.SessionIntakeRevision]:
        stmt = (
            select(models.SessionIntakeRevision)
            .where(models.SessionIntakeRevision.session_id == session_id)
            .order_by(models.SessionIntakeRevision.created_at)
        )
        result = self._db.execute(stmt)
        return list(result.scalars())

    def save_planning_context(self, session_id: str, context: dict[str, Any]) -> None:
        self._db.merge(
            models.SessionPlanningContext(session_id=session_id, context=context)
        )
        self._db.flush()

    def delete_planning_context(self, session_id: str) -> None:
        self._db.execute(
            delete(models.SessionPlanningContext).where(
                models.SessionPlanningContext.session_id == session_id
            )
        )
        self._db.flush()

    def get_planning_context(self, session_id: str) -> Optional[dict[str, Any]]:
        record = self._db.get(models.SessionPlanningContext, session_id)
        return None if record is None else record.context

    def save_optimization_result(
        self,
        session_id: str,
        result: dict[str, Any],
        engine_index: Optional[int],
        advisor_index: Optional[int],
    ) -> None:
        self._db.merge(
            models.SessionOptimizationResult(
                session_id=session_id,
                result=result,
                engine_recommended_index=engine_index,
                advisor_recommended_index=advisor_index,
            )
        )
        self._db.flush()

    def delete_optimization_result(self, session_id: str) -> None:
        self._db.execute(
            delete(models.SessionOptimizationResult).where(
                models.SessionOptimizationResult.session_id == session_id
            )
        )
        self._db.flush()

    def get_optimization_result(
        self, session_id: str
    ) -> Optional[models.SessionOptimizationResult]:
        return self._db.get(models.SessionOptimizationResult, session_id)

    def list_sessions_for_user(
        self, user_id: str, limit: Optional[int] = None
    ) -> list[models.UserSession]:
        stmt = (
            select(models.UserSession)
            .where(models.UserSession.user_id == user_id)
            .order_by(models.UserSession.updated_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = self._db.execute(stmt)
        return list(result.scalars())

    def delete_session(self, session_id: str) -> None:
        record = self._db.get(models.UserSession, session_id)
        if record:
            self._db.delete(record)
            self._db.flush()
