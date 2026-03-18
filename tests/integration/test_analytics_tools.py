"""Integration tests for GET /v1/analytics/tools — Story 4.3.

TDD: written before the endpoint exists.
All tests should be RED until the implementation is in place.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.api.dependencies import _key_cache
from prompt_ledger.models.project import ApiKey, Project, hash_api_key
from prompt_ledger.models.span import Span


async def _seed_tool_span(
    db: AsyncSession,
    project_id,
    tool_name: str,
    success: bool,
    duration_ms: int = 300,
    trace_id: str = "trace-tools",
) -> Span:
    span = Span(
        trace_id=trace_id,
        name=f"{tool_name}_call",
        kind="tool",
        tool_name=tool_name,
        success=success,
        duration_ms=duration_ms,
        status="ok" if success else "error",
        project_id=project_id,
    )
    db.add(span)
    await db.flush()
    return span


async def _get_project_id(db: AsyncSession, key: str):
    from sqlalchemy import select

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(key))
    )
    return result.scalar_one().project_id


class TestToolAnalyticsEndpoint:
    async def test_returns_one_row_per_tool_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Scenario: analytics returns one row per tool_name."""
        project_id = await _get_project_id(db_session, "test-key")

        for _ in range(6):
            await _seed_tool_span(db_session, project_id, "web_search", success=True)
        for i in range(2):
            # 2 of 6 web_search calls fail
            await _seed_tool_span(
                db_session,
                project_id,
                "web_search",
                success=False,
                trace_id=f"t-fail-{i}",
            )
        for _ in range(4):
            await _seed_tool_span(
                db_session, project_id, "db_lookup", success=True, trace_id="trace-db"
            )
        await db_session.flush()

        resp = await client.get(
            "/v1/analytics/tools", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        tools = resp.json()
        tool_names = {t["tool_name"] for t in tools}
        assert "web_search" in tool_names
        assert "db_lookup" in tool_names

    async def test_error_rate_calculated_correctly(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Scenario: error rate is correct (2 failed out of 6 = ~0.333)."""
        project_id = await _get_project_id(db_session, "test-key")

        # 4 successes + 2 failures for web_search
        for i in range(4):
            await _seed_tool_span(
                db_session, project_id, "web_search", success=True, trace_id=f"ok-{i}"
            )
        for i in range(2):
            await _seed_tool_span(
                db_session, project_id, "web_search", success=False, trace_id=f"err-{i}"
            )
        # 4 successes for db_lookup
        for i in range(4):
            await _seed_tool_span(
                db_session, project_id, "db_lookup", success=True, trace_id=f"db-{i}"
            )
        await db_session.flush()

        resp = await client.get(
            "/v1/analytics/tools", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        by_name = {t["tool_name"]: t for t in resp.json()}

        ws = by_name["web_search"]
        assert abs(ws["error_rate"] - (2 / 6)) < 0.01
        assert by_name["db_lookup"]["error_rate"] == 0.0

    async def test_response_includes_call_count_and_avg_latency(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Scenario: each entry includes call_count, error_rate, avg_duration_ms."""
        project_id = await _get_project_id(db_session, "test-key")
        for i in range(3):
            await _seed_tool_span(
                db_session,
                project_id,
                "paper_fetch",
                success=True,
                duration_ms=200,
                trace_id=f"pf-{i}",
            )
        await db_session.flush()

        resp = await client.get(
            "/v1/analytics/tools", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        entry = next(t for t in resp.json() if t["tool_name"] == "paper_fetch")
        assert entry["call_count"] == 3
        assert "error_rate" in entry
        assert "avg_duration_ms" in entry

    async def test_empty_list_when_no_tool_spans(self, client: AsyncClient):
        """Scenario: returns empty list with 200 when no tool spans exist."""
        resp = await client.get(
            "/v1/analytics/tools", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_scoped_to_project(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Endpoint only returns tools for the calling project."""
        # Create a second project
        other_project = Project(name="other-tools-project")
        db_session.add(other_project)
        await db_session.flush()
        db_session.add(
            ApiKey(
                key_hash=hash_api_key("other-key"),
                project_id=other_project.project_id,
                label="other test key",
            )
        )
        await db_session.flush()

        # Seed a tool span for the other project
        db_session.add(
            Span(
                trace_id="other-trace",
                name="secret_tool_call",
                kind="tool",
                tool_name="secret_tool",
                success=True,
                duration_ms=100,
                project_id=other_project.project_id,
            )
        )
        await db_session.flush()

        # Default project should not see the other project's tools
        _key_cache.clear()
        resp = await client.get(
            "/v1/analytics/tools", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        tool_names = {t["tool_name"] for t in resp.json()}
        assert "secret_tool" not in tool_names
