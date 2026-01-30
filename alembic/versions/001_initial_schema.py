"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-01-19 11:17:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums if they don't exist (using DO blocks for idempotency)
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE prompt_version_status AS ENUM ('draft', 'active', 'deprecated');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE execution_mode AS ENUM ('sync', 'async');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE execution_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'canceled');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE provider_name AS ENUM ('openai');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """
    )

    # Create prompts table
    op.create_table(
        "prompts",
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.TEXT(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=True),
        sa.Column("owner_team", sa.TEXT(), nullable=True),
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
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("prompt_id"),
        sa.UniqueConstraint("name"),
    )

    # Create prompt_versions table
    op.create_table(
        "prompt_versions",
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("template_source", sa.TEXT(), nullable=False),
        sa.Column("checksum_hash", sa.TEXT(), nullable=False),
        sa.Column("created_by", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"], ["prompts.prompt_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint("prompt_id", "version_number", name="uq_prompt_version"),
        sa.UniqueConstraint("prompt_id", "checksum_hash", name="uq_prompt_checksum"),
    )

    # Create models table
    op.create_table(
        "models",
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "provider",
            sa.TEXT(),
            nullable=False,
        ),
        sa.Column("model_name", sa.TEXT(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False, default=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model_id"),
        sa.UniqueConstraint("provider", "model_name"),
    )

    # Create executions table
    op.create_table(
        "executions",
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("environment", sa.TEXT(), nullable=False, default="dev"),
        sa.Column(
            "execution_mode",
            sa.TEXT(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.TEXT(),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("correlation_id", sa.TEXT(), nullable=True),
        sa.Column("idempotency_key", sa.TEXT(), nullable=True),
        sa.Column("rendered_prompt", sa.TEXT(), nullable=False),
        sa.Column("response_text", sa.TEXT(), nullable=True),
        sa.Column("temperature", sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=True),
        sa.Column("top_p", sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column("repetition_penalty", sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column("max_new_tokens", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("response_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.TEXT(), nullable=True),
        sa.Column("error_message", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["model_id"], ["models.model_id"]),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.prompt_id"]),
        sa.ForeignKeyConstraint(["version_id"], ["prompt_versions.version_id"]),
        sa.PrimaryKeyConstraint("execution_id"),
    )

    # Create execution_inputs table
    op.create_table(
        "execution_inputs",
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "variables_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("execution_id"),
    )

    # Create indexes
    op.create_index(
        "idx_exec_prompt_time", "executions", ["prompt_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "idx_exec_version_time",
        "executions",
        ["version_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_exec_status_time", "executions", ["status", sa.text("created_at DESC")]
    )
    op.create_index("idx_exec_corr", "executions", ["correlation_id"])
    op.create_index(
        "uq_exec_idempotency",
        "executions",
        ["prompt_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Add foreign key constraint for active_version_id
    op.create_foreign_key(
        "fk_prompts_active_version",
        "prompts",
        "prompt_versions",
        ["active_version_id"],
        ["version_id"],
    )

    # Convert TEXT columns to use enum types (workaround for async SQLAlchemy enum creation issues)
    # Must drop defaults first, then alter type, then re-add defaults with proper enum casting

    # prompt_versions.status - has default
    op.execute("ALTER TABLE prompt_versions ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE prompt_versions ALTER COLUMN status TYPE prompt_version_status USING status::prompt_version_status"
    )
    op.execute(
        "ALTER TABLE prompt_versions ALTER COLUMN status SET DEFAULT 'draft'::prompt_version_status"
    )

    # models.provider - no default
    op.execute(
        "ALTER TABLE models ALTER COLUMN provider TYPE provider_name USING provider::provider_name"
    )

    # executions.execution_mode - no default
    op.execute(
        "ALTER TABLE executions ALTER COLUMN execution_mode TYPE execution_mode USING execution_mode::execution_mode"
    )

    # executions.status - has default
    op.execute("ALTER TABLE executions ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE executions ALTER COLUMN status TYPE execution_status USING status::execution_status"
    )
    op.execute(
        "ALTER TABLE executions ALTER COLUMN status SET DEFAULT 'queued'::execution_status"
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("uq_exec_idempotency", table_name="executions")
    op.drop_index("idx_exec_corr", table_name="executions")
    op.drop_index("idx_exec_status_time", table_name="executions")
    op.drop_index("idx_exec_version_time", table_name="executions")
    op.drop_index("idx_exec_prompt_time", table_name="executions")

    # Drop tables
    op.drop_table("execution_inputs")
    op.drop_table("executions")
    op.drop_table("models")
    op.drop_table("prompt_versions")
    op.drop_table("prompts")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS provider_name")
    op.execute("DROP TYPE IF EXISTS execution_status")
    op.execute("DROP TYPE IF EXISTS execution_mode")
    op.execute("DROP TYPE IF EXISTS prompt_version_status")
