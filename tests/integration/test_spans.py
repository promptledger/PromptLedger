"""Integration tests for tool call span schema — Story 4.1.

TDD: written before the schemas.py and endpoint changes exist.
All tests should be RED until the implementation is in place.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestToolSpanIngestion:
    """Test that POST /v1/spans correctly validates and stores tool call fields."""

    async def test_tool_span_with_all_structured_fields_accepted(
        self, client: AsyncClient
    ):
        """Scenario: tool span with all structured fields accepted → 201."""
        resp = await client.post(
            "/v1/spans",
            json={
                "trace_id": "trace-tool-001",
                "name": "web_search_call",
                "kind": "tool",
                "tool_name": "web_search",
                "tool_args": {"query": "climate change"},
                "tool_result": {"hits": [{"title": "NASA report"}]},
                "success": True,
                "duration_ms": 340,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201
        assert "span_id" in resp.json()

    async def test_tool_span_with_only_name_and_success_accepted(
        self, client: AsyncClient
    ):
        """Scenario: tool span with only tool_name and success is accepted → 201."""
        resp = await client.post(
            "/v1/spans",
            json={
                "trace_id": "trace-tool-002",
                "name": "db_lookup_call",
                "kind": "tool",
                "tool_name": "db_lookup",
                "success": False,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201

    async def test_tool_span_without_tool_name_rejected(self, client: AsyncClient):
        """Scenario: tool span without tool_name is rejected → 422."""
        resp = await client.post(
            "/v1/spans",
            json={
                "trace_id": "trace-tool-003",
                "name": "some_tool",
                "kind": "tool",
                # tool_name omitted
                "success": True,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422
        body = resp.json()
        detail_str = str(body.get("detail", ""))
        assert "tool_name required for kind=tool" in detail_str

    async def test_non_tool_span_with_tool_name_rejected(self, client: AsyncClient):
        """Scenario: non-tool span with tool_name is rejected → 422."""
        resp = await client.post(
            "/v1/spans",
            json={
                "trace_id": "trace-tool-004",
                "name": "llm_call",
                "kind": "llm.generation",
                "tool_name": "web_search",
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422
        body = resp.json()
        detail_str = str(body.get("detail", ""))
        assert "tool_name only valid for kind=tool" in detail_str

    async def test_existing_llm_span_unaffected_by_migration(self, client: AsyncClient):
        """Scenario: existing non-tool spans can still be ingested and queried."""
        # Ingest an LLM span (no tool fields)
        resp = await client.post(
            "/v1/spans",
            json={
                "trace_id": "trace-llm-compat",
                "name": "extraction",
                "kind": "llm.generation",
                "model": "claude-haiku-4-5-20251001",
                "prompt_tokens": 150,
                "completion_tokens": 80,
                "duration_ms": 900,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 201

        # Retrieve the trace — should include the span
        resp2 = await client.get(
            "/v1/traces/trace-llm-compat",
            headers={"X-API-Key": "test-key"},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["span_count"] == 1
        span = data["spans"][0]
        assert span["tool_name"] is None
        assert span["success"] is None

    async def test_tool_span_fields_returned_in_trace(self, client: AsyncClient):
        """Tool call fields are present in GET /v1/traces/{id} span dicts."""
        await client.post(
            "/v1/spans",
            json={
                "trace_id": "trace-tool-ret",
                "name": "paper_fetch_call",
                "kind": "tool",
                "tool_name": "paper_fetch",
                "tool_args": {"doi": "10.1234/test"},
                "tool_result": {"abstract": "..."},
                "success": True,
                "duration_ms": 210,
            },
            headers={"X-API-Key": "test-key"},
        )

        resp = await client.get(
            "/v1/traces/trace-tool-ret",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        span = resp.json()["spans"][0]
        assert span["tool_name"] == "paper_fetch"
        assert span["success"] is True
