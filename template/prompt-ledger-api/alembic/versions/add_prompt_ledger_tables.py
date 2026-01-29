"""Add PromptLedger tables

Revision ID: add_prompt_ledger
Revises:
Create Date: 2024-01-29 16:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision = "add_prompt_ledger"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Prompts table
    op.create_table(
        "prompts",
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "mode", sa.Enum("full", "tracking", name="promptmode"), nullable=False
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_team", sa.String(length=100), nullable=True),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("prompt_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_prompts_name"), "prompts", ["name"], unique=False)

    # Prompt versions table
    op.create_table(
        "prompt_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("template_source", sa.Text(), nullable=False),
        sa.Column("checksum_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "draft", "archived", name="versionstatus"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["prompts.prompt_id"],
        ),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint("prompt_id", "checksum_hash"),
    )
    op.create_index(
        op.f("ix_prompt_versions_prompt_id"),
        "prompt_versions",
        ["prompt_id"],
        unique=False,
    )

    # Models table
    op.create_table(
        "models",
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("supports_streaming", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model_id"),
        sa.UniqueConstraint("provider", "model_name"),
    )

    # Executions table
    op.create_table(
        "executions",
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "execution_mode",
            sa.Enum("sync", "async", name="executionmode"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "succeeded", "failed", name="executionstatus"),
            nullable=False,
        ),
        sa.Column("rendered_prompt", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("response_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.model_id"],
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["prompts.prompt_id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["prompt_versions.version_id"],
        ),
        sa.PrimaryKeyConstraint("execution_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        op.f("ix_executions_prompt_id"), "executions", ["prompt_id"], unique=False
    )
    op.create_index(
        op.f("ix_executions_status"), "executions", ["status"], unique=False
    )

    # Execution inputs table
    op.create_table(
        "execution_inputs",
        sa.Column("input_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "variables_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "model_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.execution_id"],
        ),
        sa.PrimaryKeyConstraint("input_id"),
    )

    # Spans table for workflow tracking
    op.create_table(
        "spans",
        sa.Column("span_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.String(length=100), nullable=False),
        sa.Column("parent_span_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "output_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.execution_id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_span_id"],
            ["spans.span_id"],
        ),
        sa.PrimaryKeyConstraint("span_id"),
    )
    op.create_index(op.f("ix_spans_trace_id"), "spans", ["trace_id"], unique=False)
    op.create_index(
        op.f("ix_spans_execution_id"), "spans", ["execution_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_spans_execution_id"), table_name="spans")
    op.drop_index(op.f("ix_spans_trace_id"), table_name="spans")
    op.drop_table("spans")
    op.drop_table("execution_inputs")
    op.drop_index(op.f("ix_executions_status"), table_name="executions")
    op.drop_index(op.f("ix_executions_prompt_id"), table_name="executions")
    op.drop_table("executions")
    op.drop_table("models")
    op.drop_index(op.f("ix_prompt_versions_prompt_id"), table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index(op.f("ix_prompts_name"), table_name="prompts")
    op.drop_table("prompts")
    op.execute("DROP TYPE IF EXISTS promptmode")
    op.execute("DROP TYPE IF EXISTS versionstatus")
    op.execute("DROP TYPE IF EXISTS executionmode")
    op.execute("DROP TYPE IF EXISTS executionstatus")
