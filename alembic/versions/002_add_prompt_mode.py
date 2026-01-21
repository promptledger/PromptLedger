"""Add mode field to prompts table

Revision ID: 002
Revises: 001
Create Date: 2026-01-19 12:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add prompt mode support for dual-mode management."""

    # Create prompt_mode enum (if it doesn't exist)
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE prompt_mode AS ENUM ('full', 'tracking');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """
    )

    # Add mode column to prompts table (if it doesn't exist)
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE prompts ADD COLUMN mode prompt_mode NOT NULL DEFAULT 'full';
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """
    )

    # Create index for mode-based queries (if it doesn't exist)
    op.execute(
        """
        DO $$ BEGIN
            CREATE INDEX idx_prompts_mode ON prompts (mode);
        EXCEPTION
            WHEN duplicate_table THEN null;
        END $$;
    """
    )


def downgrade() -> None:
    """Remove prompt mode support."""

    # Drop index
    op.drop_index("idx_prompts_mode", table_name="prompts")

    # Drop column
    op.drop_column("prompts", "mode")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS prompt_mode")
