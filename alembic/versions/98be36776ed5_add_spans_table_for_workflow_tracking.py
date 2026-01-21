"""Add spans table for workflow tracking

Revision ID: 98be36776ed5
Revises: 002
Create Date: 2026-01-20 13:00:00

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "98be36776ed5"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create spans table for workflow execution tracking (FR-001)."""
    # Create spans table
    op.create_table(
        "spans",
        sa.Column("span_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", sa.String(length=100), nullable=False),
        sa.Column("parent_span_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column(
            "start_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "output_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Add foreign keys
    op.create_foreign_key(
        "fk_spans_parent_span",
        "spans",
        "spans",
        ["parent_span_id"],
        ["span_id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_spans_execution",
        "spans",
        "executions",
        ["execution_id"],
        ["execution_id"],
        ondelete="CASCADE",
    )

    # Create indexes for performance
    op.create_index("idx_span_trace_id", "spans", ["trace_id"])
    op.create_index("idx_span_parent_id", "spans", ["parent_span_id"])
    op.create_index("idx_span_execution_id", "spans", ["execution_id"], unique=True)
    op.create_index("idx_span_trace_start", "spans", ["trace_id", "start_time"])


def downgrade() -> None:
    """Drop spans table."""
    op.drop_index("idx_span_trace_start", table_name="spans")
    op.drop_index("idx_span_execution_id", table_name="spans")
    op.drop_index("idx_span_parent_id", table_name="spans")
    op.drop_index("idx_span_trace_id", table_name="spans")
    op.drop_table("spans")
