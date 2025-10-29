"""create view exposing transcript-safe session messages

Revision ID: 20240921_000002
Revises: 20240906_000001
Create Date: 2024-09-21 00:00:02
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20240921_000002"
down_revision = "20240906_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW session_transcript_messages AS
        SELECT id,
               session_id,
               role,
               content,
               created_at
        FROM session_messages
        WHERE role IN ('user', 'assistant', 'system', 'developer')
          AND COALESCE(content ->> 'type', '') NOT IN (
                'reasoning',
                'function_call',
                'function_call_output',
                'tool_result'
          );
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS session_transcript_messages;")
