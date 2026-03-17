"""End-to-end tests against the live Railway deployment.

These tests validate the complete PromptLedger stack — API, Postgres, Redis,
and Celery worker — using the promptledger-client SDK.

Run:
    export PROMPTLEDGER_URL=https://your-api.up.railway.app
    export PROMPTLEDGER_API_KEY=your-key
    pytest tests/e2e/ -v
"""

import uuid

import httpx
import pytest
from promptledger_client import (
    AsyncPromptLedgerClient,
    RegistrationPayload,
    SpanPayload,
)
from promptledger_client.context import (
    current_trace_id,
    set_parent_span_id,
    start_trace,
)
from promptledger_client.exceptions import AuthError

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# 1. Health
# ---------------------------------------------------------------------------


async def test_health(client: AsyncPromptLedgerClient):
    """API is reachable and healthy."""
    result = await client.health()
    assert result is True, "Health check failed — is the Railway service running?"


# ---------------------------------------------------------------------------
# 2. Auth enforcement
# ---------------------------------------------------------------------------


async def test_wrong_key_returns_401(base_url: str):
    """/v1/* endpoints reject invalid API keys."""
    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key="definitely-wrong-key"
    ) as bad_client:
        with pytest.raises(AuthError):
            await bad_client.get_trace_summary("any-trace-id")


async def test_health_requires_no_key(base_url: str):
    """/health is accessible without an API key."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as http:
        resp = await http.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. Prompt registration
# ---------------------------------------------------------------------------


async def test_register_code_dry_run(client: AsyncPromptLedgerClient):
    """Dry-run returns action report without writing to DB."""
    prompts = [
        RegistrationPayload(
            name=f"e2e.dry_run.{uuid.uuid4().hex[:8]}",
            template="Summarise: {{text}}",
        )
    ]
    result = await client.register_code_prompts(prompts, dry_run=True)
    assert result.dry_run is True
    assert result.registered + result.updated + result.unchanged == len(prompts)
    assert len(result.details) == len(prompts)
    assert result.details[0]["action"] == "new"


async def test_register_code_live(client: AsyncPromptLedgerClient):
    """Live registration writes a new prompt and returns action=new."""
    name = f"e2e.live.{uuid.uuid4().hex[:8]}"
    prompts = [RegistrationPayload(name=name, template="Hello {{name}}")]

    result = await client.register_code_prompts(prompts)
    assert result.dry_run is False
    assert result.registered == 1
    assert result.details[0]["action"] == "new"

    # Re-register same template → unchanged
    result2 = await client.register_code_prompts(prompts)
    assert result2.unchanged == 1
    assert result2.details[0]["action"] == "unchanged"

    # Re-register modified template → update
    prompts[0].template = "Hello {{name}} — updated"
    result3 = await client.register_code_prompts(prompts)
    assert result3.updated == 1
    assert result3.details[0]["action"] == "update"


# ---------------------------------------------------------------------------
# 4. Span ingestion + trace retrieval
# ---------------------------------------------------------------------------


async def test_log_span_returns_span_id(client: AsyncPromptLedgerClient):
    """POST /v1/spans returns a UUID span_id."""
    trace_id = f"e2e-{uuid.uuid4().hex}"
    span_id = await client.log_span(
        SpanPayload(
            trace_id=trace_id,
            name="e2e.test_span",
            kind="llm.generation",
            status="ok",
        )
    )
    assert isinstance(span_id, str)
    assert len(span_id) > 0


async def test_full_trace_workflow(client: AsyncPromptLedgerClient):
    """Log a parent + two child spans, retrieve the trace tree and summary."""
    trace_id = f"e2e-{uuid.uuid4().hex}"

    # Phase span (root)
    phase_id = await client.log_span(
        SpanPayload(
            trace_id=trace_id,
            name="e2e.phase",
            kind="workflow.phase",
            status="ok",
        )
    )

    # Agent turn (child of phase)
    turn_id = await client.log_span(
        SpanPayload(
            trace_id=trace_id,
            parent_span_id=phase_id,
            agent_id="e2e_agent",
            prompt_name="e2e.test_prompt",
            name="e2e.agent_turn",
            kind="llm.generation",
            model="claude-sonnet-4-6",
            prompt_tokens=412,
            completion_tokens=198,
            duration_ms=1340,
            status="ok",
        )
    )

    # Guardrail child span
    await client.log_span(
        SpanPayload(
            trace_id=trace_id,
            parent_span_id=turn_id,
            agent_id="guardrail",
            name="e2e.guardrail_check",
            kind="guardrail.check",
            model="claude-sonnet-4-6",
            prompt_tokens=200,
            completion_tokens=42,
            duration_ms=890,
            status="ok",
            attributes={"violations_found": 0},
        )
    )

    # Retrieve trace summary
    summary = await client.get_trace_summary(trace_id)

    assert summary.trace_id == trace_id
    assert summary.span_count == 3
    assert summary.total_prompt_tokens == 612  # 412 + 200
    assert summary.total_completion_tokens == 240  # 198 + 42
    assert summary.total_cost is not None and summary.total_cost > 0
    assert len(summary.by_agent) == 2  # e2e_agent + guardrail


async def test_trace_not_found(client: AsyncPromptLedgerClient):
    """GET /v1/traces/{id}/summary returns 404 for unknown trace."""
    from promptledger_client.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await client.get_trace_summary("no-such-trace-id-xyz")


# ---------------------------------------------------------------------------
# 5. Context helpers
# ---------------------------------------------------------------------------


async def test_context_trace_id_propagates():
    """start_trace() / current_trace_id() work correctly."""
    trace_id = start_trace()
    assert current_trace_id() == trace_id


async def test_context_parent_span_id():
    """set_parent_span_id / current_parent_span_id work correctly."""
    set_parent_span_id("span-abc")
    from promptledger_client.context import current_parent_span_id

    assert current_parent_span_id() == "span-abc"


# ---------------------------------------------------------------------------
# 6. Analytics
# ---------------------------------------------------------------------------


async def test_analytics_agents_endpoint(
    client: AsyncPromptLedgerClient, base_url: str, api_key: str
):
    """GET /v1/analytics/agents returns a valid response."""
    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key},
        timeout=30,
    ) as http:
        resp = await http.get("/v1/analytics/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
