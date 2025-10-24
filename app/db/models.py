"""SQLAlchemy ORM models for persistent chat sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class."""


class UserSession(Base):
    """Represents a chat session owned by a user."""

    __tablename__ = "user_sessions"

    session_id: Mapped[str] = mapped_column(String(length=64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(length=64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list["SessionMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    timeline_snapshot: Mapped["SessionTimelineSnapshot"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    planning_context: Mapped["SessionPlanningContext"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    optimization_result: Mapped["SessionOptimizationResult"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    intake_revisions: Mapped[list["SessionIntakeRevision"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionMessage(Base):
    """Stores conversation history for a session."""

    __tablename__ = "session_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(length=64),
        ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(length=32), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[UserSession] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_session_messages_session_created", "session_id", "created_at"),
    )


class SessionTimelineSnapshot(Base):
    """Stores the latest timeline state for a session."""

    __tablename__ = "session_timeline_snapshots"

    session_id: Mapped[str] = mapped_column(
        String(length=64),
        ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    session: Mapped[UserSession] = relationship(back_populates="timeline_snapshot")


class SessionIntakeRevision(Base):
    """Stores intake revisions per session."""

    __tablename__ = "session_intake_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(length=64),
        ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_latest: Mapped[bool] = mapped_column(default=True, nullable=False)

    session: Mapped[UserSession] = relationship(back_populates="intake_revisions")

    __table_args__ = (Index("ix_session_intake_latest", "session_id", "is_latest"),)


class SessionPlanningContext(Base):
    """Stores the active planning context for a session."""

    __tablename__ = "session_planning_contexts"

    session_id: Mapped[str] = mapped_column(
        String(length=64),
        ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    session: Mapped[UserSession] = relationship(back_populates="planning_context")


class SessionOptimizationResult(Base):
    """Stores the latest optimization result for a session."""

    __tablename__ = "session_optimization_results"

    session_id: Mapped[str] = mapped_column(
        String(length=64),
        ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    engine_recommended_index: Mapped[int | None] = mapped_column(nullable=True)
    advisor_recommended_index: Mapped[int | None] = mapped_column(nullable=True)

    session: Mapped[UserSession] = relationship(back_populates="optimization_result")
