"""create persistent session tables

Revision ID: 20240906_000001
Revises: None
Create Date: 2024-09-06 00:00:01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240906_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_user_sessions_user_updated",
        "user_sessions",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "session_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_session_messages_session_created",
        "session_messages",
        ["session_id", "created_at", "id"],
    )

    op.create_table(
        "session_timeline_snapshots",
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "session_intake_revisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.JSON(), nullable=False),
        sa.Column(
            "is_latest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_session_intake_latest",
        "session_intake_revisions",
        ["session_id", "is_latest"],
    )

    op.create_table(
        "session_planning_contexts",
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "session_optimization_results",
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("engine_recommended_index", sa.Integer(), nullable=True),
        sa.Column("advisor_recommended_index", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("session_optimization_results")
    op.drop_table("session_planning_contexts")
    op.drop_index("ix_session_intake_latest", table_name="session_intake_revisions")
    op.drop_table("session_intake_revisions")
    op.drop_table("session_timeline_snapshots")
    op.drop_index("ix_session_messages_session_created", table_name="session_messages")
    op.drop_table("session_messages")
    op.drop_index("ix_user_sessions_user_updated", table_name="user_sessions")
    op.drop_table("user_sessions")
