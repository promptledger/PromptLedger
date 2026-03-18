"""Add projects and api_keys tables for multi-tenant namespacing — Story 2.1

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-03-18

Non-destructive: adds new tables only. All existing data continues to work.
The default project and env-var API key are seeded at application startup
(idempotent), not in this migration.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_projects_name"),
    )

    op.create_table(
        "api_keys",
        sa.Column(
            "key_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "is_system_key",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )

    op.create_index("idx_api_keys_project_id", "api_keys", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_api_keys_project_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("projects")
