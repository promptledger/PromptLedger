"""Tests for database models."""

from uuid import uuid4

import pytest

from prompt_ledger.models.execution import Execution, ExecutionInput
from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum


class TestPromptModel:
    """Test prompt model functionality."""

    async def test_compute_checksum(self):
        """Test checksum computation."""
        template = "Hello {{name}}"
        checksum1 = compute_checksum(template)
        checksum2 = compute_checksum(template)

        assert checksum1 == checksum2
        assert len(checksum1) == 64  # SHA-256 hex length

    async def test_prompt_creation(self, db_session):
        """Test creating a prompt."""
        prompt = Prompt(
            name="test_prompt",
            description="Test description",
            owner_team="AI-Platform",
        )
        db_session.add(prompt)
        await db_session.commit()

        assert prompt.prompt_id is not None
        assert prompt.name == "test_prompt"
        assert prompt.created_at is not None

    async def test_prompt_version_creation(self, db_session):
        """Test creating a prompt version."""
        # Create prompt first
        prompt = Prompt(name="test_prompt")
        db_session.add(prompt)
        await db_session.flush()

        # Create version
        version = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=1,
            template_source="Hello {{name}}",
            checksum_hash=compute_checksum("Hello {{name}}"),
            status="active",
        )
        db_session.add(version)
        await db_session.commit()

        assert version.version_id is not None
        assert version.version_number == 1
        assert version.status == "active"


class TestExecutionModel:
    """Test execution model functionality."""

    async def test_execution_creation(self, db_session):
        """Test creating an execution."""
        # Create related objects
        prompt = Prompt(name="test_prompt")
        db_session.add(prompt)

        model = Model(
            provider="openai",
            model_name="gpt-4o-mini",
            max_tokens=128000,
        )
        db_session.add(model)

        await db_session.flush()

        version = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=1,
            template_source="Hello {{name}}",
            checksum_hash=compute_checksum("Hello {{name}}"),
        )
        db_session.add(version)
        await db_session.flush()

        # Create execution
        execution = Execution(
            prompt_id=prompt.prompt_id,
            version_id=version.version_id,
            model_id=model.model_id,
            execution_mode="sync",
            status="succeeded",
            rendered_prompt="Hello World",
            response_text="Hi there!",
            latency_ms=500,
        )
        db_session.add(execution)
        await db_session.flush()

        # Create execution input
        execution_input = ExecutionInput(
            execution_id=execution.execution_id,
            variables_json={"name": "World"},
        )
        db_session.add(execution_input)
        await db_session.commit()

        assert execution.execution_id is not None
        assert execution.status == "succeeded"
        assert execution.execution_input is not None
        assert execution.execution_input.variables_json == {"name": "World"}


class TestModel:
    """Test AI model configuration."""

    async def test_model_creation(self, db_session):
        """Test creating a model configuration."""
        model = Model(
            provider="openai",
            model_name="gpt-4o",
            max_tokens=128000,
            supports_streaming=True,
        )
        db_session.add(model)
        await db_session.commit()

        assert model.model_id is not None
        assert model.provider == "openai"
        assert model.model_name == "gpt-4o"
        assert model.supports_streaming is True
