"""Integration tests for execution model resolution (bugfix).

Covers the two 500-causing bugs in _resolve_execution_context:
  1. KeyError when "model" key is absent from the request body
  2. TypeError when "model" is a plain string (client SDK sends str, not dict)

TDD: written BEFORE the fix. Must fail (RED) first.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum

MOCK_GENERATE = {
    "response_text": "mocked",
    "prompt_tokens": 10,
    "response_tokens": 5,
    "latency_ms": 50,
}

ANTHROPIC_PATCH = "prompt_ledger.services.providers.AnthropicAdapter.generate"
OPENAI_PATCH = "prompt_ledger.services.providers.OpenAIAdapter.generate"


async def _seed(db: AsyncSession, model_name="claude-sonnet-4-6", provider="anthropic"):
    model = Model(
        model_id=uuid.uuid4(),
        provider=provider,
        model_name=model_name,
        max_tokens=200000,
    )
    db.add(model)

    prompt = Prompt(
        name=f"srf.test.{uuid.uuid4().hex[:8]}", mode="tracking", description="test"
    )
    db.add(prompt)
    await db.flush()

    template = "You are a helpful agent."
    version = PromptVersion(
        prompt_id=prompt.prompt_id,
        version_number=1,
        template_source=template,
        checksum_hash=compute_checksum(template),
        status="active",
    )
    db.add(version)
    await db.flush()
    prompt.active_version_id = version.version_id
    await db.commit()
    return prompt, model


class TestExecutionModelResolution:
    """Model-resolution bugs exposed by SRF 500 errors."""

    async def test_no_model_field_uses_default(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Request without 'model' key should not 500 — falls back to claude-sonnet-4-6."""
        prompt, _ = await _seed(db_session, "claude-sonnet-4-6", "anthropic")

        with patch(ANTHROPIC_PATCH, new=AsyncMock(return_value=MOCK_GENERATE)):
            resp = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": prompt.name,
                    "messages": [{"role": "user", "content": "hello"}],
                    # no "model" key — this is what SRF sends
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["response_text"] == "mocked"

    async def test_model_as_string_resolves_by_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Request with model as a plain string should resolve by model_name."""
        prompt, _ = await _seed(db_session, "claude-opus-4-6", "anthropic")

        with patch(ANTHROPIC_PATCH, new=AsyncMock(return_value=MOCK_GENERATE)):
            resp = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": prompt.name,
                    "model": "claude-opus-4-6",  # string, not dict — SDK sends this
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["response_text"] == "mocked"

    async def test_model_as_dict_still_works(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Existing dict form must not regress."""
        prompt, _ = await _seed(db_session, "gpt-4o-mini", "openai")

        with patch(OPENAI_PATCH, new=AsyncMock(return_value=MOCK_GENERATE)):
            resp = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": prompt.name,
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )

        assert resp.status_code == 200, resp.text

    async def test_unknown_string_model_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """model='nonexistent-model' → 400, not 500."""
        prompt, _ = await _seed(db_session)

        resp = await client.post(
            "/v1/executions/run",
            headers={"X-API-Key": "test-key"},
            json={
                "prompt_name": prompt.name,
                "model": "nonexistent-model-xyz",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        assert resp.status_code == 400, resp.text

    async def test_missing_default_model_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """If no model provided and claude-sonnet-4-6 not in DB → 400, not 500."""
        # Seed a prompt but no claude-sonnet-4-6 model
        prompt = Prompt(
            name=f"srf.nomodel.{uuid.uuid4().hex[:8]}",
            mode="tracking",
            description="test",
        )
        db_session.add(prompt)
        await db_session.flush()
        template = "test"
        version = PromptVersion(
            prompt_id=prompt.prompt_id,
            version_number=1,
            template_source=template,
            checksum_hash=compute_checksum(template),
            status="active",
        )
        db_session.add(version)
        await db_session.flush()
        prompt.active_version_id = version.version_id
        await db_session.commit()

        resp = await client.post(
            "/v1/executions/run",
            headers={"X-API-Key": "test-key"},
            json={
                "prompt_name": prompt.name,
                # no model, no claude-sonnet-4-6 in DB
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        assert resp.status_code == 400, resp.text
