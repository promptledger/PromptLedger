"""Integration tests for execution telemetry — Story 1.8.

TDD: written BEFORE the implementation. Must fail (RED) first.

All tests require Docker (Postgres at postgres:5432).
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


async def _seed_model(
    db: AsyncSession,
    model_name: str,
    provider: str = "openai",
) -> Model:
    model = Model(
        model_id=uuid.uuid4(),
        provider=provider,
        model_name=model_name,
        max_tokens=4096,
    )
    db.add(model)
    await db.flush()
    return model


async def _seed_prompt_with_version(
    db: AsyncSession,
    name: str,
    mode: str = "full",
) -> tuple[Prompt, PromptVersion]:
    prompt = Prompt(name=name, mode=mode, description="test")
    db.add(prompt)
    await db.flush()

    version = PromptVersion(
        prompt_id=prompt.prompt_id,
        version_number=1,
        template_source=f"Template {{{{var}}}}",
        checksum_hash=compute_checksum(f"Template {{{{var}}}}"),
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
    prompt_tokens: int = 200,
    response_tokens: int = 80,
    model_name: str | None = None,
) -> Execution:
    execution = Execution(
        execution_id=uuid.uuid4(),
        prompt_id=prompt.prompt_id,
        version_id=version.version_id,
        model_id=model.model_id,
        execution_mode="sync",
        status="succeeded",
        rendered_prompt="test rendered prompt",
        prompt_tokens=prompt_tokens,
        response_tokens=response_tokens,
        model_name=model_name or model.model_name,
    )
    db.add(execution)
    await db.flush()
    return execution


# ---------------------------------------------------------------------------
# Tests — GET /v1/executions/{id} telemetry
# ---------------------------------------------------------------------------


class TestGetExecutionTelemetry:
    """GET /v1/executions/{id} includes model_name, provider, total_cost."""

    async def test_get_execution_telemetry_has_model_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /v1/executions/{id} telemetry includes model_name field."""
        model = await _seed_model(db_session, "gpt-4o-mini")
        prompt, version = await _seed_prompt_with_version(
            db_session, "tel-test-get-model-name"
        )
        execution = await _seed_execution(db_session, prompt, version, model)
        await db_session.commit()

        response = await client.get(
            f"/v1/executions/{execution.execution_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "telemetry" in data
        assert data["telemetry"]["model_name"] == "gpt-4o-mini"

    async def test_get_execution_telemetry_has_provider(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /v1/executions/{id} telemetry includes provider field."""
        model = await _seed_model(db_session, "gpt-4o-mini", provider="openai")
        prompt, version = await _seed_prompt_with_version(
            db_session, "tel-test-get-provider"
        )
        execution = await _seed_execution(db_session, prompt, version, model)
        await db_session.commit()

        response = await client.get(
            f"/v1/executions/{execution.execution_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["telemetry"]["provider"] == "openai"

    async def test_get_execution_telemetry_has_total_cost(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /v1/executions/{id} telemetry includes total_cost field."""
        model = await _seed_model(db_session, "gpt-4o-mini")
        prompt, version = await _seed_prompt_with_version(
            db_session, "tel-test-get-cost"
        )
        execution = await _seed_execution(
            db_session, prompt, version, model, prompt_tokens=2000, response_tokens=1000
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/executions/{execution.execution_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        # gpt-4o-mini: 2000 in * 0.00015/1k + 1000 out * 0.00060/1k = 0.00090
        assert data["telemetry"]["total_cost"] == pytest.approx(0.00090, rel=1e-4)

    async def test_get_execution_telemetry_unknown_model_cost_is_null(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Unknown model name → total_cost is null in telemetry."""
        model = await _seed_model(db_session, "some-future-model-xyz")
        prompt, version = await _seed_prompt_with_version(
            db_session, "tel-test-unknown-model"
        )
        execution = await _seed_execution(db_session, prompt, version, model)
        await db_session.commit()

        response = await client.get(
            f"/v1/executions/{execution.execution_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["telemetry"]["total_cost"] is None


# ---------------------------------------------------------------------------
# Tests — GET /v1/executions/ list includes model_name
# ---------------------------------------------------------------------------


class TestListExecutionsModelName:
    """GET /v1/executions/ list entries include model_name."""

    async def test_list_executions_includes_model_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Each entry in the executions list includes model_name."""
        model = await _seed_model(db_session, "gpt-4o-mini")
        prompt, version = await _seed_prompt_with_version(
            db_session, "tel-test-list-model"
        )
        await _seed_execution(db_session, prompt, version, model)
        await db_session.commit()

        response = await client.get(
            "/v1/executions/",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) >= 1
        entry = next(
            e for e in data["executions"] if e.get("model_name") == "gpt-4o-mini"
        )
        assert entry["model_name"] == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Tests — POST /v1/executions:submit response includes model_name, provider
# ---------------------------------------------------------------------------


class TestSubmitAsyncResponseFields:
    """POST /v1/executions:submit response includes model_name and provider."""

    async def test_submit_response_includes_model_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Async submit response includes model_name."""
        # Seed a model and prompt to submit against
        model = await _seed_model(db_session, "gpt-4o-mini")
        prompt, version = await _seed_prompt_with_version(
            db_session, "tel-submit-model-name"
        )
        await db_session.commit()

        response = await client.post(
            "/v1/executions:submit",
            headers={"X-API-Key": "test-key"},
            json={
                "prompt_name": "tel-submit-model-name",
                "environment": "test",
                "variables": {"var": "hello"},
                "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
            },
        )
        # Note: Celery task dispatch may fail in test environment but the
        # immediate response should include model_name before the task is queued.
        # If Celery is not configured, the endpoint should still return the fields.
        assert response.status_code == 200
        data = response.json()
        assert data["model_name"] == "gpt-4o-mini"
        assert data["provider"] == "openai"
