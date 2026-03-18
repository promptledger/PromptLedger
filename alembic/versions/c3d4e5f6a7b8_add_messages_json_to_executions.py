"""add messages_json to executions and make rendered_prompt nullable

Revision ID: c3d4e5f6a7b8
Revises: eb819e059121
Create Date: 2026-03-18 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "eb819e059121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make rendered_prompt nullable to support messages-only executions
    op.alter_column("executions", "rendered_prompt", nullable=True)
    # Add messages_json JSONB column for FR-003 messages input
    op.add_column(
        "executions",
        sa.Column(
            "messages_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("executions", "messages_json")
    op.alter_column("executions", "rendered_prompt", nullable=False)
