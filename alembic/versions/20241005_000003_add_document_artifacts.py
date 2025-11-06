"""add session document artifacts table

Revision ID: 20241005_000003
Revises: 20240921_000002
Create Date: 2024-10-05 00:00:03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20241005_000003"
down_revision = "20240921_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_document_artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column(
            "document_type",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("extract", sa.JSON(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_session_document_artifacts_session_updated",
        "session_document_artifacts",
        ["session_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_document_artifacts_session_updated",
        table_name="session_document_artifacts",
    )
    op.drop_table("session_document_artifacts")
