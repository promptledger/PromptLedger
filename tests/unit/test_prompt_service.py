"""Test prompt service functionality."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum
from prompt_ledger.services.prompt_service import PromptService


class TestPromptServiceCodeBased:
    """Test code-based prompt registration."""

    @pytest.mark.asyncio
    async def test_register_new_code_prompt(self, db_session: AsyncSession):
        """Test registering a new code-based prompt."""
        # Arrange
        service = PromptService(db_session)
        template = "Hello {{name}}!"
        prompts_data = [
            {
                "name": "WELCOME",
                "template_source": template,
                "template_hash": compute_checksum(template),
            }
        ]

        # Act
        result = await service.register_code_prompts(prompts_data)

        # Assert
        assert len(result) == 1
        assert result[0]["name"] == "WELCOME"
        assert result[0]["mode"] == "tracking"
        assert result[0]["version"] == 1
        assert result[0]["change_detected"] is False  # First registration
        assert result[0]["previous_version"] is None

    @pytest.mark.asyncio
    async def test_register_unchanged_prompt_no_new_version(
        self, db_session: AsyncSession
    ):
        """Test re-registering unchanged prompt doesn't create new version."""
        # Arrange
        service = PromptService(db_session)
        template = "Hello {{name}}!"
        prompts_data = [
            {
                "name": "WELCOME",
                "template_source": template,
                "template_hash": compute_checksum(template),
            }
        ]

        # Act - Register twice
        result1 = await service.register_code_prompts(prompts_data)
        result2 = await service.register_code_prompts(prompts_data)

        # Assert
        assert result1[0]["version"] == 1
        assert result2[0]["version"] == 1  # Same version
        assert result2[0]["change_detected"] is False
        assert result2[0]["previous_version"] is None

    @pytest.mark.asyncio
    async def test_register_changed_prompt_creates_new_version(
        self, db_session: AsyncSession
    ):
        """Test changing template content creates new version."""
        # Arrange
        service = PromptService(db_session)
        template_v1 = "Hello {{name}}!"
        template_v2 = "Hi {{name}}, welcome!"

        # Act - Register, then update
        result1 = await service.register_code_prompts(
            [
                {
                    "name": "WELCOME",
                    "template_source": template_v1,
                    "template_hash": compute_checksum(template_v1),
                }
            ]
        )

        result2 = await service.register_code_prompts(
            [
                {
                    "name": "WELCOME",
                    "template_source": template_v2,
                    "template_hash": compute_checksum(template_v2),
                }
            ]
        )

        # Assert
        assert result1[0]["version"] == 1
        assert result2[0]["version"] == 2
        assert result2[0]["change_detected"] is True
        assert result2[0]["previous_version"] == 1

    @pytest.mark.asyncio
    async def test_register_multiple_prompts_at_once(self, db_session: AsyncSession):
        """Test registering multiple prompts in one call."""
        # Arrange
        service = PromptService(db_session)
        prompts_data = [
            {
                "name": "WELCOME",
                "template_source": "Hello {{name}}!",
                "template_hash": compute_checksum("Hello {{name}}!"),
            },
            {
                "name": "GOODBYE",
                "template_source": "Goodbye {{name}}!",
                "template_hash": compute_checksum("Goodbye {{name}}!"),
            },
        ]

        # Act
        result = await service.register_code_prompts(prompts_data)

        # Assert
        assert len(result) == 2
        assert result[0]["name"] == "WELCOME"
        assert result[0]["version"] == 1
        assert result[1]["name"] == "GOODBYE"
        assert result[1]["version"] == 1

    @pytest.mark.asyncio
    async def test_register_prompt_sets_tracking_mode(self, db_session: AsyncSession):
        """Test that registered prompts are set to tracking mode."""
        # Arrange
        service = PromptService(db_session)
        prompts_data = [
            {
                "name": "CODE_PROMPT",
                "template_source": "Test {{var}}",
                "template_hash": compute_checksum("Test {{var}}"),
            }
        ]

        # Act
        await service.register_code_prompts(prompts_data)

        # Assert - Query database to verify mode
        from sqlalchemy import select

        result = await db_session.execute(
            select(Prompt).where(Prompt.name == "CODE_PROMPT")
        )
        prompt = result.scalar_one()
        assert prompt.mode == "tracking"

    @pytest.mark.asyncio
    async def test_register_sets_active_version(self, db_session: AsyncSession):
        """Test that registered prompt has active version set."""
        # Arrange
        service = PromptService(db_session)
        prompts_data = [
            {
                "name": "ACTIVE_TEST",
                "template_source": "Test",
                "template_hash": compute_checksum("Test"),
            }
        ]

        # Act
        await service.register_code_prompts(prompts_data)

        # Assert
        from sqlalchemy import select

        result = await db_session.execute(
            select(Prompt).where(Prompt.name == "ACTIVE_TEST")
        )
        prompt = result.scalar_one()
        assert prompt.active_version_id is not None


class TestModeValidation:
    """Test mode validation logic."""

    @pytest.mark.asyncio
    async def test_validate_full_mode_prompt(self, db_session: AsyncSession):
        """Test validating full mode prompt."""
        # Arrange
        service = PromptService(db_session)
        prompt = Prompt(name="full_prompt", mode="full")
        db_session.add(prompt)
        await db_session.commit()

        # Act & Assert - Should not raise
        result = await service.validate_mode("full_prompt", "full", "PUT operation")
        assert result.name == "full_prompt"
        assert result.mode == "full"

    @pytest.mark.asyncio
    async def test_validate_tracking_mode_prompt(self, db_session: AsyncSession):
        """Test validating tracking mode prompt."""
        # Arrange
        service = PromptService(db_session)
        prompt = Prompt(name="tracking_prompt", mode="tracking")
        db_session.add(prompt)
        await db_session.commit()

        # Act & Assert - Should not raise
        result = await service.validate_mode(
            "tracking_prompt", "tracking", "execute operation"
        )
        assert result.name == "tracking_prompt"
        assert result.mode == "tracking"

    @pytest.mark.asyncio
    async def test_validate_mode_mismatch_raises_error(self, db_session: AsyncSession):
        """Test mode mismatch raises HTTPException."""
        # Arrange
        service = PromptService(db_session)
        prompt = Prompt(name="tracking_prompt", mode="tracking")
        db_session.add(prompt)
        await db_session.commit()

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.validate_mode("tracking_prompt", "full", "PUT operation")

        assert exc_info.value.status_code == 400
        assert "tracking" in exc_info.value.detail.lower()
        assert "code-based" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_validate_full_mode_mismatch_error_message(
        self, db_session: AsyncSession
    ):
        """Test error message for full mode prompt accessed via code endpoint."""
        # Arrange
        service = PromptService(db_session)
        prompt = Prompt(name="full_prompt", mode="full")
        db_session.add(prompt)
        await db_session.commit()

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.validate_mode("full_prompt", "tracking", "execute operation")

        assert exc_info.value.status_code == 400
        assert "full mode" in exc_info.value.detail.lower()
        assert "PUT" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_validate_nonexistent_prompt_raises_404(
        self, db_session: AsyncSession
    ):
        """Test validating non-existent prompt raises 404."""
        # Arrange
        service = PromptService(db_session)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.validate_mode("nonexistent", "full", "operation")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_register_empty_list_returns_empty(self, db_session: AsyncSession):
        """Test registering empty list returns empty result."""
        # Arrange
        service = PromptService(db_session)

        # Act
        result = await service.register_code_prompts([])

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_version_increment_handles_gaps(self, db_session: AsyncSession):
        """Test version numbering is sequential even with manual version creation."""
        # Arrange
        service = PromptService(db_session)
        prompt = Prompt(name="gap_test", mode="tracking")
        db_session.add(prompt)
        await db_session.flush()

        # Manually create version with gap (skip version 2)
        version1 = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=1,
            template_source="v1",
            checksum_hash=compute_checksum("v1"),
            status="active",
        )
        version3 = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=3,
            template_source="v3",
            checksum_hash=compute_checksum("v3"),
            status="active",
        )
        db_session.add(version1)
        db_session.add(version3)
        await db_session.commit()

        # Act - Register new version
        result = await service.register_code_prompts(
            [
                {
                    "name": "gap_test",
                    "template_source": "v4",
                    "template_hash": compute_checksum("v4"),
                }
            ]
        )

        # Assert - Should be max + 1 = 4
        assert result[0]["version"] == 4
