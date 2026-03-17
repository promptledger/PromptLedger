"""Integration tests for cost calculation wired into analytics — Story 1.4.

TDD: these tests are written BEFORE the analytics.py changes.
They must fail (RED) first, then go GREEN after analytics is updated.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.execution import Execution
from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_model(db: AsyncSession, model_name: str) -> Model:
    model = Model(
        model_id=uuid.uuid4(),
        provider="openai",
        model_name=model_name,
        max_tokens=4096,
    )
    db.add(model)
    await db.flush()
    return model


async def _seed_prompt_with_version(
    db: AsyncSession, name: str, mode: str = "full"
) -> tuple[Prompt, PromptVersion]:
    prompt = Prompt(name=name, mode=mode, description="test")
    db.add(prompt)
    await db.flush()

    version = PromptVersion(
        prompt_id=prompt.prompt_id,
        version_number=1,
        template_source=f"Template for {name} {{{{var}}}}",
        checksum_hash=compute_checksum(f"Template for {name} {{{{var}}}}"),
        status="active",
    )
    db.add(version)
    await db.flush()

    prompt.active_version_id = version.version_id
    await db.flush()
    return prompt, version


async def _seed_execution(
    db: AsyncSession,
    prompt: Prompt,
    version: PromptVersion,
    model: Model,
    prompt_tokens: int,
    response_tokens: int,
) -> Execution:
    execution = Execution(
        execution_id=uuid.uuid4(),
        prompt_id=prompt.prompt_id,
        version_id=version.version_id,
        model_id=model.model_id,
        execution_mode="sync",
        rendered_prompt="test rendered prompt",
        prompt_tokens=prompt_tokens,
        response_tokens=response_tokens,
    )
    db.add(execution)
    await db.flush()
    return execution


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyticsCostFieldPresent:
    """Analytics mode-specific response includes total_cost field."""

    async def test_mode_full_response_includes_total_cost_field(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /v1/analytics/prompts?mode=full response includes total_cost key."""
        response = await client.get(
            "/v1/analytics/prompts?mode=full",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_cost" in data

    async def test_mode_tracking_response_includes_total_cost_field(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /v1/analytics/prompts?mode=tracking response includes total_cost key."""
        response = await client.get(
            "/v1/analytics/prompts?mode=tracking",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_cost" in data


class TestAnalyticsCostCalculation:
    """total_cost is correctly computed from execution token counts and model pricing."""

    async def test_single_execution_known_model_computes_correct_cost(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Known model execution produces the correct total_cost in analytics.

        gpt-4o-mini: input $0.00015/1k, output $0.00060/1k
        2000 input + 1000 output = (2 * 0.00015) + (1 * 0.00060) = 0.00030 + 0.00060 = 0.00090
        """
        model = await _seed_model(db_session, "gpt-4o-mini")
        prompt, version = await _seed_prompt_with_version(
            db_session, "cost-test-prompt-1"
        )
        await _seed_execution(db_session, prompt, version, model, 2000, 1000)
        await db_session.commit()

        response = await client.get(
            "/v1/analytics/prompts?mode=full",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_cost"] == pytest.approx(0.00090, rel=1e-4)

    async def test_multiple_executions_same_model_sums_cost(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Multiple executions with the same model sum their costs correctly.

        gpt-4o-mini:
          exec 1: 2000 in / 1000 out → 0.00090
          exec 2: 1000 in / 500 out  → 0.00045
          total → 0.00135
        """
        model = await _seed_model(db_session, "gpt-4o-mini")
        prompt, version = await _seed_prompt_with_version(
            db_session, "cost-test-prompt-2"
        )
        await _seed_execution(db_session, prompt, version, model, 2000, 1000)
        await _seed_execution(db_session, prompt, version, model, 1000, 500)
        await db_session.commit()

        response = await client.get(
            "/v1/analytics/prompts?mode=full",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_cost"] == pytest.approx(0.00135, rel=1e-4)

    async def test_no_executions_returns_zero_cost(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """With no executions, total_cost is 0.0 (not null — zero is not unknown)."""
        response = await client.get(
            "/v1/analytics/prompts?mode=full",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_cost"] == pytest.approx(0.0)

    async def test_mode_filtering_does_not_bleed_across_modes(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Executions for mode=full are not counted toward mode=tracking cost."""
        model = await _seed_model(db_session, "gpt-4o-mini")

        # full-mode prompt with an execution
        full_prompt, full_version = await _seed_prompt_with_version(
            db_session, "full-cost-bleed", mode="full"
        )
        await _seed_execution(db_session, full_prompt, full_version, model, 2000, 1000)

        # tracking-mode prompt with no executions
        await _seed_prompt_with_version(
            db_session, "tracking-cost-bleed", mode="tracking"
        )

        await db_session.commit()

        # Tracking mode should have $0 cost (no executions for tracking prompts)
        response = await client.get(
            "/v1/analytics/prompts?mode=tracking",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_cost"] == pytest.approx(0.0)

        # Full mode should have the gpt-4o-mini cost
        response = await client.get(
            "/v1/analytics/prompts?mode=full",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_cost"] == pytest.approx(0.00090, rel=1e-4)
