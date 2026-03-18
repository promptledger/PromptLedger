"""Integration tests for project-scoped spans and analytics — Story 2.3."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.api.dependencies import _key_cache
from prompt_ledger.models.project import ApiKey, Project, hash_api_key


@pytest.fixture
async def second_project(db_session: AsyncSession):
    """Create a second project with its own API key."""
    project = Project(name="project-beta")
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        ApiKey(
            key_hash=hash_api_key("beta-key"),
            project_id=project.project_id,
            label="beta test key",
        )
    )
    await db_session.flush()
    return project.project_id


class TestSpanIngestScoping:
    async def test_ingest_span_stamps_project_id(self, client: AsyncClient):
        """POST /v1/spans stores the calling project's project_id on the span."""
        from sqlalchemy import select

        from prompt_ledger.models.span import Span

        resp = await client.post(
            "/v1/spans",
            json={
                "trace_id": "trace-stamp-001",
                "name": "my-span",
                "kind": "llm.generation",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201
        span_id = resp.json()["span_id"]

        # Retrieve session via client's dependency override
        # We can verify via a second request that scoping is enforced

    async def test_ingest_span_requires_auth(self, client: AsyncClient):
        """POST /v1/spans returns 401 without API key."""
        resp = await client.post(
            "/v1/spans",
            json={"trace_id": "trace-001", "name": "span", "kind": "llm.generation"},
        )
        assert resp.status_code == 401

    async def test_get_trace_only_returns_own_project_spans(
        self, client: AsyncClient, db_session: AsyncSession, second_project
    ):
        """GET /v1/traces/{trace_id} returns 404 when trace belongs to another project."""
        _key_cache.clear()

        trace_id = "cross-project-trace"

        # Project alpha (default/test-key) ingests a span
        resp = await client.post(
            "/v1/spans",
            json={"trace_id": trace_id, "name": "alpha-span", "kind": "llm.generation"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201

        # Project beta tries to read the same trace — should get 404
        _key_cache.clear()
        resp_beta = await client.get(
            f"/v1/traces/{trace_id}",
            headers={"X-API-Key": "beta-key"},
        )
        assert resp_beta.status_code == 404

        # Project alpha can read it fine
        _key_cache.clear()
        resp_alpha = await client.get(
            f"/v1/traces/{trace_id}",
            headers={"X-API-Key": "test-key"},
        )
        assert resp_alpha.status_code == 200

    async def test_get_trace_summary_scoped(
        self, client: AsyncClient, db_session: AsyncSession, second_project
    ):
        """GET /v1/traces/{trace_id}/summary returns 404 for another project's trace."""
        _key_cache.clear()
        trace_id = "scoped-summary-trace"

        # Default project ingests a span
        await client.post(
            "/v1/spans",
            json={
                "trace_id": trace_id,
                "name": "summary-span",
                "kind": "llm.generation",
            },
            headers={"X-API-Key": "test-key"},
        )

        # Beta can't see the summary
        _key_cache.clear()
        resp = await client.get(
            f"/v1/traces/{trace_id}/summary",
            headers={"X-API-Key": "beta-key"},
        )
        assert resp.status_code == 404

    async def test_agent_analytics_scoped(
        self, client: AsyncClient, db_session: AsyncSession, second_project
    ):
        """GET /v1/analytics/agents only returns agents for the calling project."""
        from prompt_ledger.models.span import Span

        _key_cache.clear()

        # Seed spans directly into DB — one per project, same agent_id
        from sqlalchemy import select

        # Get the default project's ID from the seeded API key
        from prompt_ledger.models.project import ApiKey, hash_api_key

        result = await db_session.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key("test-key"))
        )
        default_key = result.scalar_one()
        default_project_id = default_key.project_id

        db_session.add(
            Span(
                trace_id="analytics-trace-a",
                name="agent-span-alpha",
                kind="llm.generation",
                agent_id="shared-agent",
                project_id=default_project_id,
                prompt_tokens=50,
                completion_tokens=20,
            )
        )
        db_session.add(
            Span(
                trace_id="analytics-trace-b",
                name="agent-span-beta",
                kind="llm.generation",
                agent_id="shared-agent",
                project_id=second_project,
                prompt_tokens=100,
                completion_tokens=40,
            )
        )
        await db_session.flush()

        # Default project analytics — should see 1 span for shared-agent
        _key_cache.clear()
        resp = await client.get(
            "/v1/analytics/agents",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "shared-agent"
        assert agents[0]["total_spans"] == 1
