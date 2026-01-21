"""Test prompt mode functionality."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum


class TestPromptMode:
    """Test prompt mode field and operations."""

    @pytest.mark.asyncio
    async def test_prompt_defaults_to_full_mode(self, db_session: AsyncSession):
        """Test that new prompts default to 'full' mode."""
        # Arrange & Act
        prompt = Prompt(name="test_prompt", description="Test")
        db_session.add(prompt)
        await db_session.commit()
        await db_session.refresh(prompt)

        # Assert
        assert prompt.mode == "full", "New prompts should default to 'full' mode"

    @pytest.mark.asyncio
    async def test_prompt_can_be_created_with_tracking_mode(
        self, db_session: AsyncSession
    ):
        """Test creating prompt in tracking mode."""
        # Arrange & Act
        prompt = Prompt(name="code_prompt", mode="tracking")
        db_session.add(prompt)
        await db_session.commit()
        await db_session.refresh(prompt)

        # Assert
        assert prompt.mode == "tracking", "Prompt mode should be 'tracking'"

    @pytest.mark.asyncio
    async def test_prompt_mode_can_be_queried(self, db_session: AsyncSession):
        """Test querying prompts by mode."""
        # Arrange
        full_prompt = Prompt(name="full_prompt", mode="full")
        tracking_prompt = Prompt(name="tracking_prompt", mode="tracking")
        db_session.add(full_prompt)
        db_session.add(tracking_prompt)
        await db_session.commit()

        # Act - Query full mode prompts
        result = await db_session.execute(select(Prompt).where(Prompt.mode == "full"))
        full_prompts = result.scalars().all()

        # Assert
        assert len(full_prompts) == 1
        assert full_prompts[0].name == "full_prompt"

        # Act - Query tracking mode prompts
        result = await db_session.execute(
            select(Prompt).where(Prompt.mode == "tracking")
        )
        tracking_prompts = result.scalars().all()

        # Assert
        assert len(tracking_prompts) == 1
        assert tracking_prompts[0].name == "tracking_prompt"

    @pytest.mark.asyncio
    async def test_mode_index_exists(self, db_session: AsyncSession):
        """Test that mode index exists for query optimization."""
        # Act - Query information_schema to check index existence
        result = await db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'prompts' AND indexname = 'idx_prompts_mode'"
            )
        )
        index = result.scalar_one_or_none()

        # Assert
        assert index == "idx_prompts_mode", "Mode index should exist for performance"

    @pytest.mark.asyncio
    async def test_mode_field_not_nullable(self, db_session: AsyncSession):
        """Test that mode field cannot be null."""
        # This test verifies the migration set nullable=False
        # Query column metadata
        result = await db_session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'prompts' AND column_name = 'mode'"
            )
        )
        is_nullable = result.scalar_one_or_none()

        # Assert
        assert is_nullable == "NO", "Mode field should be NOT NULL"

    @pytest.mark.asyncio
    async def test_full_and_tracking_prompts_can_have_same_version_structure(
        self, db_session: AsyncSession
    ):
        """Test that both modes use the same versioning structure."""
        # Arrange
        full_prompt = Prompt(name="full_versioned", mode="full")
        tracking_prompt = Prompt(name="tracking_versioned", mode="tracking")
        db_session.add(full_prompt)
        db_session.add(tracking_prompt)
        await db_session.flush()

        # Act - Create versions for both
        full_version = PromptVersion(
            prompt_id=full_prompt.prompt_id,
            version_number=1,
            template_source="Template {{var}}",
            checksum_hash=compute_checksum("Template {{var}}"),
            status="active",
        )
        tracking_version = PromptVersion(
            prompt_id=tracking_prompt.prompt_id,
            version_number=1,
            template_source="Code {{var}}",
            checksum_hash=compute_checksum("Code {{var}}"),
            status="active",
        )
        db_session.add(full_version)
        db_session.add(tracking_version)
        await db_session.commit()

        # Assert - Both should work with same version table
        result = await db_session.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_id == full_prompt.prompt_id
            )
        )
        assert result.scalar_one() is not None

        result = await db_session.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_id == tracking_prompt.prompt_id
            )
        )
        assert result.scalar_one() is not None
