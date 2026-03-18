"""End-to-end tests against the live Railway deployment.

These tests validate the complete PromptLedger stack — API, Postgres, Redis,
and Celery worker — using the promptledger-client SDK.

Run:
    export PROMPTLEDGER_URL=https://your-api.up.railway.app
    export PROMPTLEDGER_API_KEY=your-key   # admin/default-project system key
    pytest tests/e2e/ -v

Epic coverage:
    Sections 1-7  — Epic 1 (span ingestion, analytics, execute() with messages)
    Section 8     — Epic 2 (project namespacing, admin API)
    Section 9     — Epic 3 (async execution with span context)
    Section 10    — Epic 4 (tool call capture, analytics/tools)
"""

import asyncio
import os
import time
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
            template_source="Summarise: {{text}}",
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
    prompts = [RegistrationPayload(name=name, template_source="Hello {{name}}")]

    result = await client.register_code_prompts(prompts)
    assert result.dry_run is False
    assert result.registered == 1
    assert result.details[0]["action"] == "new"

    # Re-register same template → unchanged
    result2 = await client.register_code_prompts(prompts)
    assert result2.unchanged == 1
    assert result2.details[0]["action"] == "unchanged"

    # Re-register modified template → update
    prompts[0].template_source = "Hello {{name}} — updated"
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


# ---------------------------------------------------------------------------
# 7. execute() with messages — FR-003
# ---------------------------------------------------------------------------


@pytest.fixture
def require_anthropic_key():
    """Skip the test if ANTHROPIC_API_KEY is not set in the environment."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — skipping Anthropic execute() e2e test")


async def test_execute_with_messages_returns_span_id(
    client: AsyncPromptLedgerClient,
    base_url: str,
    api_key: str,
    require_anthropic_key,
):
    """POST /v1/executions/run with messages + span block returns span_id and 200."""
    trace_id = f"e2e-exec-{uuid.uuid4().hex}"
    prompt_name = f"e2e.execute.{uuid.uuid4().hex[:8]}"

    await client.register_code_prompts(
        [
            RegistrationPayload(
                name=prompt_name,
                template_source="You are a concise assistant. {{noop}}",
            )
        ]
    )

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=60,
    ) as http:
        resp = await http.post(
            "/v1/executions/run",
            json={
                "prompt_name": prompt_name,
                "messages": [
                    {"role": "system", "content": "You are a concise assistant."},
                    {"role": "user", "content": "Reply with exactly: ok"},
                ],
                "model": {
                    "provider": "anthropic",
                    "model_name": "claude-haiku-4-5-20251001",
                },
                "params": {"max_tokens": 10},
                "environment": "e2e",
                "span": {
                    "trace_id": trace_id,
                    "kind": "llm.generation",
                    "agent_id": "e2e_runner",
                },
            },
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "succeeded"
    assert isinstance(body.get("response_text"), str) and len(body["response_text"]) > 0

    span_id = body.get("span_id")
    assert span_id is not None, "span_id missing — auto-span not created"
    assert len(span_id) == 36, f"span_id doesn't look like a UUID: {span_id!r}"

    tel = body.get("telemetry", {})
    assert tel.get("prompt_tokens", 0) > 0
    assert tel.get("completion_tokens", 0) > 0


async def test_execute_span_appears_in_trace_summary(
    client: AsyncPromptLedgerClient,
    base_url: str,
    api_key: str,
    require_anthropic_key,
):
    """Auto-created span is queryable via GET /v1/traces/{trace_id}/summary."""
    trace_id = f"e2e-exec-trace-{uuid.uuid4().hex}"
    prompt_name = f"e2e.execute.{uuid.uuid4().hex[:8]}"

    await client.register_code_prompts(
        [RegistrationPayload(name=prompt_name, template_source="Assistant: {{noop}}")]
    )

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=60,
    ) as http:
        exec_resp = await http.post(
            "/v1/executions/run",
            json={
                "prompt_name": prompt_name,
                "messages": [{"role": "user", "content": "Say: done"}],
                "model": {
                    "provider": "anthropic",
                    "model_name": "claude-haiku-4-5-20251001",
                },
                "params": {"max_tokens": 10},
                "environment": "e2e",
                "span": {"trace_id": trace_id, "agent_id": "e2e_runner"},
            },
        )
    assert exec_resp.status_code == 200

    summary = await client.get_trace_summary(trace_id)
    assert summary.trace_id == trace_id
    assert summary.span_count >= 1
    assert summary.total_prompt_tokens > 0

    agents = [a["agent_id"] for a in summary.by_agent]
    assert "e2e_runner" in agents


# ---------------------------------------------------------------------------
# 8. Admin API — Epic 2 (project namespacing)
# ---------------------------------------------------------------------------
# The admin key is the same as PROMPTLEDGER_API_KEY: it is the default
# project's system key, seeded at startup from the API_KEY env var.
# ---------------------------------------------------------------------------


async def test_admin_create_project_and_issue_key(base_url: str, api_key: str):
    """POST /v1/admin/projects creates a project and returns a plaintext API key."""
    project_slug = f"e2e-proj-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=30,
    ) as http:
        resp = await http.post(
            "/v1/admin/projects",
            json={"name": project_slug, "key_label": f"{project_slug}-key"},
        )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "project_id" in body
    assert body["name"] == project_slug
    assert isinstance(body.get("api_key"), str) and body["api_key"].startswith("pl-")
    assert "key_id" in body


async def test_admin_issued_key_authenticates(base_url: str, api_key: str):
    """A key issued via POST /v1/admin/projects works for span ingestion."""
    project_slug = f"e2e-auth-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=30,
    ) as http:
        create_resp = await http.post(
            "/v1/admin/projects",
            json={"name": project_slug, "key_label": "auth-test"},
        )
    assert create_resp.status_code == 201
    new_key = create_resp.json()["api_key"]

    # Use the new project-scoped key to ingest a span
    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key=new_key, timeout=30.0
    ) as new_client:
        span_id = await new_client.log_span(
            SpanPayload(
                trace_id=f"e2e-new-proj-{uuid.uuid4().hex}",
                name="e2e.project_scoped_span",
                kind="llm.generation",
            )
        )
    assert isinstance(span_id, str) and len(span_id) == 36


async def test_admin_project_span_isolation(base_url: str, api_key: str):
    """Spans written by one project's key are not readable by another project."""
    project_slug = f"e2e-iso-{uuid.uuid4().hex[:8]}"
    trace_id = f"e2e-iso-trace-{uuid.uuid4().hex}"

    # Create a second project and key
    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=30,
    ) as http:
        create_resp = await http.post(
            "/v1/admin/projects",
            json={"name": project_slug, "key_label": "iso-test"},
        )
    assert create_resp.status_code == 201
    other_key = create_resp.json()["api_key"]

    # Write a span with the other project's key
    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key=other_key, timeout=30.0
    ) as other_client:
        await other_client.log_span(
            SpanPayload(
                trace_id=trace_id,
                name="e2e.other_project_span",
                kind="llm.generation",
            )
        )

    # The default project's key should get 404 for that trace
    from promptledger_client.exceptions import NotFoundError

    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key=api_key, timeout=30.0
    ) as default_client:
        with pytest.raises(NotFoundError):
            await default_client.get_trace_summary(trace_id)


async def test_admin_revoke_key_prevents_access(base_url: str, api_key: str):
    """DELETE /v1/admin/keys/{key_id} immediately invalidates the key."""
    project_slug = f"e2e-revoke-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=30,
    ) as http:
        create_resp = await http.post(
            "/v1/admin/projects",
            json={"name": project_slug, "key_label": "revoke-test"},
        )
    assert create_resp.status_code == 201
    body = create_resp.json()
    revoke_key = body["api_key"]
    key_id = body["key_id"]

    # Confirm the key works before revoke
    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key=revoke_key, timeout=30.0
    ) as test_client:
        assert await test_client.health() is True

    # Revoke the key
    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key},
        timeout=30,
    ) as http:
        del_resp = await http.delete(f"/v1/admin/keys/{key_id}")
    assert del_resp.status_code == 204

    # Key should now be rejected
    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key=revoke_key, timeout=30.0
    ) as revoked_client:
        with pytest.raises(AuthError):
            await revoked_client.get_trace_summary("any-trace")


# ---------------------------------------------------------------------------
# 9. Async execution with span context — Epic 3
# ---------------------------------------------------------------------------


async def test_submit_async_returns_202(
    base_url: str, api_key: str, require_anthropic_key
):
    """POST /v1/executions/submit returns 202 with execution_id."""
    prompt_name = f"e2e.async.{uuid.uuid4().hex[:8]}"
    trace_id = f"e2e-async-{uuid.uuid4().hex}"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=30,
    ) as http:
        # Register prompt first
        await http.post(
            "/v1/prompts/register-code",
            json={
                "prompts": [
                    {
                        "name": prompt_name,
                        "template_source": "You are helpful. {{noop}}",
                    }
                ]
            },
        )

        submit_resp = await http.post(
            "/v1/executions/submit",
            json={
                "prompt_name": prompt_name,
                "messages": [{"role": "user", "content": "Say: async ok"}],
                "model": {
                    "provider": "anthropic",
                    "model_name": "claude-haiku-4-5-20251001",
                },
                "params": {"max_tokens": 10},
                "environment": "e2e",
                "span": {"trace_id": trace_id, "agent_id": "e2e_async"},
            },
        )

    assert (
        submit_resp.status_code == 202
    ), f"Expected 202, got {submit_resp.status_code}: {submit_resp.text}"
    body = submit_resp.json()
    assert "execution_id" in body
    assert body.get("status") == "pending"


async def test_submit_async_span_context_forwarded(
    base_url: str, api_key: str, require_anthropic_key
):
    """Worker creates a span with the submitted trace_id after the provider call."""
    prompt_name = f"e2e.asyncspan.{uuid.uuid4().hex[:8]}"
    trace_id = f"e2e-async-span-{uuid.uuid4().hex}"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=60,
    ) as http:
        await http.post(
            "/v1/prompts/register-code",
            json={
                "prompts": [
                    {"name": prompt_name, "template_source": "Assistant: {{noop}}"}
                ]
            },
        )

        submit_resp = await http.post(
            "/v1/executions/submit",
            json={
                "prompt_name": prompt_name,
                "messages": [{"role": "user", "content": "Say: done"}],
                "model": {
                    "provider": "anthropic",
                    "model_name": "claude-haiku-4-5-20251001",
                },
                "params": {"max_tokens": 10},
                "environment": "e2e",
                "span": {"trace_id": trace_id, "agent_id": "e2e_async_worker"},
            },
        )
        assert submit_resp.status_code == 202
        execution_id = submit_resp.json()["execution_id"]

        # Poll for completion (max 30s)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            poll_resp = await http.get(f"/v1/executions/{execution_id}")
            if poll_resp.json().get("status") in ("succeeded", "failed"):
                break
            await asyncio.sleep(2)

        final = poll_resp.json()
        assert final["status"] == "succeeded", f"Execution did not succeed: {final}"

    # The worker should have created a span for this trace
    async with AsyncPromptLedgerClient(
        base_url=base_url, api_key=api_key, timeout=30.0
    ) as client:
        summary = await client.get_trace_summary(trace_id)
    assert summary.span_count >= 1
    agent_ids = [a["agent_id"] for a in summary.by_agent]
    assert "e2e_async_worker" in agent_ids


# ---------------------------------------------------------------------------
# 10. Tool call capture — Epic 4
# ---------------------------------------------------------------------------


async def test_log_tool_call_returns_span_id(client: AsyncPromptLedgerClient):
    """log_tool_call() submits a kind='tool' span and returns a UUID span_id."""
    trace_id = f"e2e-tool-{uuid.uuid4().hex}"

    span_id = await client.log_tool_call(
        trace_id=trace_id,
        tool_name="web_search",
        tool_args={"query": "climate change IPCC"},
        tool_result={"hits": [{"title": "IPCC 2023 Report"}]},
        success=True,
        duration_ms=310,
        agent_id="e2e_researcher",
    )
    assert isinstance(span_id, str) and len(span_id) == 36


async def test_log_tool_call_failure_logged(client: AsyncPromptLedgerClient):
    """A failed tool call is logged with success=False and error_message."""
    trace_id = f"e2e-tool-fail-{uuid.uuid4().hex}"

    span_id = await client.log_tool_call(
        trace_id=trace_id,
        tool_name="db_lookup",
        tool_args={"id": "doc-42"},
        tool_result={"error_type": "TimeoutError"},
        success=False,
        duration_ms=5000,
        error_message="connection timed out after 5 s",
    )
    assert isinstance(span_id, str) and len(span_id) == 36


async def test_tool_call_appears_in_trace(client: AsyncPromptLedgerClient):
    """A tool span logged via log_tool_call() is retrievable in the trace tree."""
    trace_id = f"e2e-tool-tree-{uuid.uuid4().hex}"

    await client.log_tool_call(
        trace_id=trace_id,
        tool_name="paper_fetch",
        tool_args={"doi": "10.1234/test"},
        tool_result={"abstract": "Climate analysis..."},
        success=True,
        duration_ms=215,
    )

    summary = await client.get_trace_summary(trace_id)
    assert summary.span_count == 1


async def test_tool_analytics_endpoint_returns_results(
    client: AsyncPromptLedgerClient, base_url: str, api_key: str
):
    """GET /v1/analytics/tools returns aggregated call_count and error_rate."""
    unique_tool = f"e2e_tool_{uuid.uuid4().hex[:8]}"
    trace_id = f"e2e-analytics-{uuid.uuid4().hex}"

    # Seed 3 calls: 2 success, 1 failure
    await client.log_tool_call(
        trace_id=trace_id,
        tool_name=unique_tool,
        tool_args={},
        tool_result={},
        success=True,
        duration_ms=100,
    )
    await client.log_tool_call(
        trace_id=trace_id,
        tool_name=unique_tool,
        tool_args={},
        tool_result={},
        success=True,
        duration_ms=200,
    )
    await client.log_tool_call(
        trace_id=trace_id,
        tool_name=unique_tool,
        tool_args={},
        tool_result={"error_type": "Timeout"},
        success=False,
        duration_ms=3000,
        error_message="timeout",
    )

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key},
        timeout=30,
    ) as http:
        resp = await http.get("/v1/analytics/tools")

    assert resp.status_code == 200
    tools = resp.json()
    entry = next((t for t in tools if t["tool_name"] == unique_tool), None)
    assert entry is not None, f"tool {unique_tool!r} not found in {tools}"
    assert entry["call_count"] == 3
    assert abs(entry["error_rate"] - (1 / 3)) < 0.01
    assert "avg_duration_ms" in entry


async def test_tool_span_invalid_without_tool_name_rejected(
    base_url: str, api_key: str
):
    """POST /v1/spans with kind='tool' but no tool_name returns 422."""
    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=30,
    ) as http:
        resp = await http.post(
            "/v1/spans",
            json={
                "trace_id": f"e2e-422-{uuid.uuid4().hex}",
                "name": "missing_tool_name",
                "kind": "tool",
                # tool_name intentionally omitted
            },
        )
    assert resp.status_code == 422
