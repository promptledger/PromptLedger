"""Add model_name column to executions table — Story 1.8

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-17
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add model_name column — nullable so existing rows are unaffected.
    op.add_column(
        "executions",
        sa.Column("model_name", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("executions", "model_name")
