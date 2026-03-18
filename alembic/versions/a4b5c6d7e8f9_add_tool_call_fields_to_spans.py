"""Add tool call fields to spans — Story 4.1

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-03-18

Adds first-class tool call columns to the spans table so that
kind='tool' spans carry structured, queryable data instead of
storing tool info in the freeform `attributes` JSONB blob.

New columns:
- tool_name  (String 200, nullable, indexed)  — stable identifier
- success    (Boolean, nullable)              — did the tool call succeed?
- tool_args  (JSONB, nullable)                — arguments passed to the tool
- tool_result (JSONB, nullable)               — return value / output

All columns are nullable so that existing non-tool spans are unaffected.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spans", sa.Column("tool_name", sa.String(200), nullable=True))
    op.add_column("spans", sa.Column("success", sa.Boolean, nullable=True))
    op.add_column(
        "spans",
        sa.Column("tool_args", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "spans",
        sa.Column(
            "tool_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_index("idx_span_tool_name", "spans", ["tool_name"])


def downgrade() -> None:
    op.drop_index("idx_span_tool_name", table_name="spans")
    op.drop_column("spans", "tool_result")
    op.drop_column("spans", "tool_args")
    op.drop_column("spans", "success")
    op.drop_column("spans", "tool_name")
