"""Extend provider_name enum to include 'anthropic'

Hotfix for Story 1.1: seed_models.py seeds Anthropic models but the
provider_name Postgres enum was created with only ('openai').  Any
INSERT with provider='anthropic' fails with a DB constraint error,
making the Anthropic adapter silently unusable.

Revision ID: a1b2c3d4e5f6
Revises: eb819e059121
Create Date: 2026-03-17
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "eb819e059121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in
    # Postgres < 12.  We are on Postgres 15+, so this is safe inside the
    # Alembic-managed transaction.  IF NOT EXISTS makes it idempotent.
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'anthropic'")


def downgrade() -> None:
    # Postgres does not support removing values from an existing enum type.
    # To fully revert: drop the column, drop the type, recreate as
    # ENUM('openai'), recreate the column.  This is destructive and is
    # left as a manual step.  The presence of 'anthropic' in the enum
    # causes no harm if no rows use it.
    pass
