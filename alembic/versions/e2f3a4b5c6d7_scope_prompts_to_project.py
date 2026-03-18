"""Scope prompts to project: add project_id, swap unique constraint — Story 2.2

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-18

Three-step migration, all in one transaction:
1. Add nullable project_id column with FK to projects
2. Backfill all existing rows to the 'default' project
3. Enforce NOT NULL; replace global UNIQUE(name) with UNIQUE(project_id, name)

Non-destructive: the column is added nullable and backfilled before enforcement.
The constraint swap happens atomically — no window where both or neither exist.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: add nullable column
    op.add_column(
        "prompts",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.project_id"),
            nullable=True,
        ),
    )

    # Step 2: backfill to the default project (created by startup seeding)
    op.execute(
        """
        UPDATE prompts
        SET project_id = (SELECT project_id FROM projects WHERE name = 'default')
        WHERE project_id IS NULL
        """
    )

    # Step 3a: enforce NOT NULL
    op.alter_column("prompts", "project_id", nullable=False)

    # Step 3b: drop global unique constraint, add scoped constraint
    op.drop_constraint("prompts_name_key", "prompts", type_="unique")
    op.create_unique_constraint(
        "uq_project_prompt_name", "prompts", ["project_id", "name"]
    )

    # Index for project scoping queries
    op.create_index("idx_prompts_project_id", "prompts", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_prompts_project_id", table_name="prompts")
    op.drop_constraint("uq_project_prompt_name", "prompts", type_="unique")
    op.create_unique_constraint("prompts_name_key", "prompts", ["name"])
    op.alter_column("prompts", "project_id", nullable=True)
    op.drop_column("prompts", "project_id")
