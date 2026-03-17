"""add agent_id and prompt_name to spans

Revision ID: eb819e059121
Revises: 98be36776ed5
Create Date: 2026-03-16 23:51:13.224520

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "eb819e059121"
down_revision = "98be36776ed5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spans", sa.Column("agent_id", sa.String(100), nullable=True))
    op.add_column("spans", sa.Column("prompt_name", sa.String(200), nullable=True))
    op.create_index("idx_span_agent_id", "spans", ["agent_id"])
    op.create_index("idx_span_prompt_name", "spans", ["prompt_name"])


def downgrade() -> None:
    op.drop_index("idx_span_prompt_name", table_name="spans")
    op.drop_index("idx_span_agent_id", table_name="spans")
    op.drop_column("spans", "prompt_name")
    op.drop_column("spans", "agent_id")
