"""Integration tests for FR-003: messages input and auto-span creation.

TDD: written BEFORE the implementation. Must fail (RED) first.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.execution import Execution
from prompt_ledger.models.model import Model
from prompt_ledger.models.prompt import Prompt, PromptVersion, compute_checksum
from prompt_ledger.models.span import Span

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_GENERATE_RESULT = {
    "response_text": "Test response from mock LLM",
    "prompt_tokens": 42,
    "response_tokens": 17,
    "latency_ms": 123,
    "provider_request_id": "mock-req-id",
}


async def _seed_model(
    db: AsyncSession,
    model_name: str = "gpt-4o-mini",
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


async def _seed_tracking_prompt(
    db: AsyncSession,
    name: str = "agent.debate_turn",
) -> tuple[Prompt, PromptVersion]:
    prompt = Prompt(name=name, mode="tracking", description="test tracking prompt")
    db.add(prompt)
    await db.flush()

    template = "You are a debater. Topic: {{topic}}"
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
    await db.flush()
    return prompt, version


async def _seed_full_prompt(
    db: AsyncSession,
    name: str = "full.summarize",
) -> tuple[Prompt, PromptVersion]:
    prompt = Prompt(name=name, mode="full", description="test full prompt")
    db.add(prompt)
    await db.flush()

    template = "Summarize: {{text}}"
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
    await db.flush()
    return prompt, version


# ---------------------------------------------------------------------------
# Tests — POST /v1/executions/run with messages input
# ---------------------------------------------------------------------------


class TestExecutionMessagesInput:
    """FR-003: POST /v1/executions/run with messages array."""

    async def test_messages_input_returns_200(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """POST /v1/executions/run with messages returns 200 and response_text."""
        model = await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.200")
        await db_session.commit()

        with patch(
            "prompt_ledger.services.providers.OpenAIAdapter.generate",
            new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
        ):
            response = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "test.messages.200",
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "messages": [{"role": "user", "content": "Hello, debate partner!"}],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "execution_id" in data
        assert data["response_text"] == "Test response from mock LLM"
        assert "telemetry" in data

    async def test_messages_stored_in_db(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """messages stored in messages_json, rendered_prompt is None."""
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.db")
        await db_session.commit()

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Discuss the topic."},
        ]

        with patch(
            "prompt_ledger.services.providers.OpenAIAdapter.generate",
            new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
        ):
            response = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "test.messages.db",
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "messages": messages,
                },
            )

        assert response.status_code == 200
        exec_id = response.json()["execution_id"]

        # Verify DB record
        result = await db_session.execute(
            select(Execution).where(Execution.execution_id == uuid.UUID(exec_id))
        )
        execution = result.scalar_one()
        assert execution.messages_json == messages
        assert execution.rendered_prompt is None

    async def test_messages_on_full_mode_prompt_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """messages input on full-mode prompt → 400."""
        await _seed_model(db_session)
        await _seed_full_prompt(db_session, "test.messages.full400")
        await db_session.commit()

        response = await client.post(
            "/v1/executions/run",
            headers={"X-API-Key": "test-key"},
            json={
                "prompt_name": "test.messages.full400",
                "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        assert response.status_code == 400
        assert "messages" in response.json()["detail"].lower()

    async def test_neither_messages_nor_variables_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """tracking prompt with neither messages nor variables → 400."""
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.neither400")
        await db_session.commit()

        response = await client.post(
            "/v1/executions/run",
            headers={"X-API-Key": "test-key"},
            json={
                "prompt_name": "test.messages.neither400",
                "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
            },
        )

        assert response.status_code == 400

    async def test_empty_messages_array_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Empty messages array → 400."""
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.empty400")
        await db_session.commit()

        response = await client.post(
            "/v1/executions/run",
            headers={"X-API-Key": "test-key"},
            json={
                "prompt_name": "test.messages.empty400",
                "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                "messages": [],
            },
        )

        assert response.status_code == 400

    async def test_span_block_creates_span_and_returns_span_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """span block in request → span_id in response and Span record created in DB."""
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.span")
        await db_session.commit()

        trace_id = str(uuid.uuid4())

        with patch(
            "prompt_ledger.services.providers.OpenAIAdapter.generate",
            new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
        ):
            response = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "test.messages.span",
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "messages": [{"role": "user", "content": "hello"}],
                    "span": {"trace_id": trace_id},
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "span_id" in data
        assert data["span_id"] is not None

        # Verify Span record in DB
        result = await db_session.execute(select(Span).where(Span.trace_id == trace_id))
        span = result.scalar_one_or_none()
        assert span is not None
        assert span.trace_id == trace_id

    async def test_no_span_block_returns_null_span_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """No span block → span_id null in response."""
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.nospan")
        await db_session.commit()

        with patch(
            "prompt_ledger.services.providers.OpenAIAdapter.generate",
            new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
        ):
            response = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "test.messages.nospan",
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data.get("span_id") is None

    async def test_span_has_correct_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Auto-created span has trace_id, parent_span_id, agent_id, tokens."""
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.spanfields")
        await db_session.commit()

        trace_id = str(uuid.uuid4())
        parent_span_id = str(uuid.uuid4())

        with patch(
            "prompt_ledger.services.providers.OpenAIAdapter.generate",
            new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
        ):
            response = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "test.messages.spanfields",
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "messages": [{"role": "user", "content": "hello"}],
                    "span": {
                        "trace_id": trace_id,
                        "parent_span_id": parent_span_id,
                        "agent_id": "debate-agent-1",
                    },
                },
            )

        assert response.status_code == 200

        result = await db_session.execute(select(Span).where(Span.trace_id == trace_id))
        span = result.scalar_one()
        assert span.agent_id == "debate-agent-1"
        assert str(span.parent_span_id) == parent_span_id
        assert span.prompt_tokens == MOCK_GENERATE_RESULT["prompt_tokens"]
        assert span.completion_tokens == MOCK_GENERATE_RESULT["response_tokens"]
        assert span.prompt_name == "test.messages.spanfields"

    async def test_span_queryable_via_trace_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Span created by execution is queryable via GET /v1/traces/{trace_id}/summary."""
        await _seed_model(db_session)
        await _seed_tracking_prompt(db_session, "test.messages.tracequery")
        await db_session.commit()

        trace_id = str(uuid.uuid4())

        with patch(
            "prompt_ledger.services.providers.OpenAIAdapter.generate",
            new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
        ):
            run_response = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "test.messages.tracequery",
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "messages": [{"role": "user", "content": "hello"}],
                    "span": {"trace_id": trace_id},
                },
            )
        assert run_response.status_code == 200

        summary_response = await client.get(
            f"/v1/traces/{trace_id}/summary",
            headers={"X-API-Key": "test-key"},
        )
        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["trace_id"] == trace_id
        assert summary["span_count"] >= 1

    async def test_variables_path_still_works(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Regression: full-mode prompt with variables still works (mode unchanged)."""
        await _seed_model(db_session)
        await _seed_full_prompt(db_session, "test.messages.regression")
        await db_session.commit()

        with patch(
            "prompt_ledger.services.providers.OpenAIAdapter.generate",
            new=AsyncMock(return_value=MOCK_GENERATE_RESULT),
        ):
            response = await client.post(
                "/v1/executions/run",
                headers={"X-API-Key": "test-key"},
                json={
                    "prompt_name": "test.messages.regression",
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "variables": {"text": "Some text to summarize."},
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["response_text"] == "Test response from mock LLM"
