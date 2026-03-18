"""Scope spans and executions to project — Story 2.3

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-03-18

Adds project_id to both spans and executions tables.

Three-step pattern (same as 2.2):
1. Add nullable project_id with FK to projects
2. Backfill existing rows to the 'default' project
3. Leave nullable (spans/executions may not need strict enforcement)

Note: We keep the column nullable post-migration to avoid breaking
existing rows from pre-namespacing deployments. All new rows created
via authenticated endpoints will always have project_id set.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- spans table ---
    op.add_column(
        "spans",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.project_id"),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE spans
        SET project_id = (SELECT project_id FROM projects WHERE name = 'default')
        WHERE project_id IS NULL
        """
    )
    op.create_index("idx_span_project_id", "spans", ["project_id"])

    # --- executions table ---
    op.add_column(
        "executions",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.project_id"),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE executions
        SET project_id = (SELECT project_id FROM projects WHERE name = 'default')
        WHERE project_id IS NULL
        """
    )
    op.create_index("idx_exec_project_id", "executions", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_exec_project_id", table_name="executions")
    op.drop_column("executions", "project_id")

    op.drop_index("idx_span_project_id", table_name="spans")
    op.drop_column("spans", "project_id")
