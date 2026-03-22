"""Integration tests for GET /v1/traces list endpoint — Stories 5.1 and 5.2.

TDD: written before implementation exists.
All tests are RED until the endpoint is added to traces_router.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prompt_ledger.models.project import Project
from prompt_ledger.models.span import Span

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _post_span(client: AsyncClient, **kwargs) -> str:
    """POST /v1/spans with sensible defaults and return span_id."""
    payload = {
        "trace_id": kwargs.get("trace_id", "trace-default"),
        "name": kwargs.get("name", "test.span"),
        "kind": kwargs.get("kind", "llm.generation"),
        "status": kwargs.get("status", "ok"),
    }
    for k in ("agent_id", "prompt_name", "model", "prompt_tokens", "completion_tokens"):
        if k in kwargs:
            payload[k] = kwargs[k]
    resp = await client.post(
        "/v1/spans", json=payload, headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["span_id"]


async def _get_project_id(db_session: AsyncSession):
    """Return the project_id for the 'default' test project."""
    result = await db_session.execute(select(Project).where(Project.name == "default"))
    return result.scalar_one().project_id


# ---------------------------------------------------------------------------
# Story 5.1 — filtering
# ---------------------------------------------------------------------------


class TestListTracesFiltering:
    """Acceptance criteria from Story 5.1."""

    async def test_filter_by_agent_id_returns_matching_traces(
        self, client: AsyncClient
    ):
        """Scenario: filter by agent_id returns matching traces only."""
        # 3 traces with agent "paper_1"
        for i in range(3):
            await _post_span(client, trace_id=f"tr-p1-{i}", agent_id="paper_1")
        # 2 traces with agent "paper_2"
        for i in range(2):
            await _post_span(client, trace_id=f"tr-p2-{i}", agent_id="paper_2")

        resp = await client.get(
            "/v1/traces",
            params={"agent_id": "paper_1"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 3
        for t in data["traces"]:
            assert t["trace_id"].startswith("tr-p1-")

    async def test_filter_by_status_error_returns_only_failed_traces(
        self, client: AsyncClient
    ):
        """Scenario: filter by status=error returns only failed traces."""
        # 2 error traces
        for i in range(2):
            await _post_span(client, trace_id=f"tr-err-{i}", status="error")
        # 3 ok traces
        for i in range(3):
            await _post_span(client, trace_id=f"tr-ok-{i}", status="ok")

        resp = await client.get(
            "/v1/traces", params={"status": "error"}, headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 2
        for t in data["traces"]:
            assert t["status"] == "error"

    async def test_filter_by_prompt_name_returns_matching_traces(
        self, client: AsyncClient
    ):
        """Scenario: filter by prompt_name returns traces containing that prompt."""
        # 2 traces with target prompt
        for i in range(2):
            await _post_span(
                client, trace_id=f"tr-pn-{i}", prompt_name="agent.debate_turn"
            )
        # 3 others
        for i in range(3):
            await _post_span(
                client, trace_id=f"tr-other-{i}", prompt_name="agent.other"
            )

        resp = await client.get(
            "/v1/traces",
            params={"prompt_name": "agent.debate_turn"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 2

    async def test_time_range_filter_limits_results(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Scenario: time range filter returns only traces started on or after 'from'."""
        project_id = await _get_project_id(db_session)
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 3 spans / traces from yesterday
        for i in range(3):
            db_session.add(
                Span(
                    trace_id=f"tr-old-{i}",
                    name="test.span",
                    kind="llm.generation",
                    start_time=yesterday,
                    project_id=project_id,
                )
            )
        # 2 spans / traces from today
        for i in range(2):
            db_session.add(
                Span(
                    trace_id=f"tr-new-{i}",
                    name="test.span",
                    kind="llm.generation",
                    start_time=now,
                    project_id=project_id,
                )
            )
        await db_session.flush()

        resp = await client.get(
            "/v1/traces",
            params={"from": start_of_today.isoformat()},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 2
        for t in data["traces"]:
            assert t["trace_id"].startswith("tr-new-")

    async def test_multiple_filters_are_anded(self, client: AsyncClient):
        """Scenario: multiple filters are ANDed together."""
        # paper_1 + error
        await _post_span(
            client, trace_id="tr-p1-err", agent_id="paper_1", status="error"
        )
        # paper_1 + ok
        await _post_span(client, trace_id="tr-p1-ok", agent_id="paper_1", status="ok")
        # paper_2 + error
        await _post_span(
            client, trace_id="tr-p2-err", agent_id="paper_2", status="error"
        )

        resp = await client.get(
            "/v1/traces",
            params={"agent_id": "paper_1", "status": "error"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 1
        assert data["traces"][0]["trace_id"] == "tr-p1-err"

    async def test_no_filters_returns_traces_with_pagination_fields(
        self, client: AsyncClient
    ):
        """Scenario: no filters returns 'traces' array and 'next_cursor' field."""
        for i in range(3):
            await _post_span(client, trace_id=f"tr-nf-{i}")

        resp = await client.get("/v1/traces", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert "traces" in data
        assert "next_cursor" in data
        assert len(data["traces"]) == 3

    async def test_invalid_status_returns_422(self, client: AsyncClient):
        """Scenario: invalid status value returns 422."""
        resp = await client.get(
            "/v1/traces",
            params={"status": "banana"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422

    async def test_trace_item_has_required_fields(self, client: AsyncClient):
        """Each trace in the list has trace_id, status, span_count, total_cost."""
        await _post_span(client, trace_id="tr-fields")

        resp = await client.get("/v1/traces", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        item = resp.json()["traces"][0]
        assert "trace_id" in item
        assert "status" in item
        assert "span_count" in item
        assert "total_cost" in item

    async def test_trace_status_is_error_when_any_span_errors(
        self, client: AsyncClient
    ):
        """A trace with a mix of ok and error spans should report status=error."""
        await _post_span(client, trace_id="tr-mixed", status="ok")
        await _post_span(client, trace_id="tr-mixed", name="fail.span", status="error")

        resp = await client.get("/v1/traces", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        item = resp.json()["traces"][0]
        assert item["trace_id"] == "tr-mixed"
        assert item["status"] == "error"
        assert item["span_count"] == 2

    async def test_project_scoping_hides_other_project_traces(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Traces from a different project should not appear in results."""
        from prompt_ledger.models.project import Project as ProjModel

        # Create a second project and insert a span under it
        other_proj = ProjModel(name="other-project")
        db_session.add(other_proj)
        await db_session.flush()
        db_session.add(
            Span(
                trace_id="tr-other-proj",
                name="spy.span",
                kind="llm.generation",
                project_id=other_proj.project_id,
            )
        )
        await db_session.flush()

        # Own project trace
        await _post_span(client, trace_id="tr-mine")

        resp = await client.get("/v1/traces", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        trace_ids = [t["trace_id"] for t in resp.json()["traces"]]
        assert "tr-other-proj" not in trace_ids
        assert "tr-mine" in trace_ids


# ---------------------------------------------------------------------------
# Story 5.2 — cursor-based pagination
# ---------------------------------------------------------------------------


class TestListTracesPagination:
    """Acceptance criteria from Story 5.2."""

    async def _insert_traces(
        self,
        n: int,
        db_session: AsyncSession,
        project_id,
    ) -> None:
        """Insert n traces (one span each) directly into the DB."""
        now = datetime.now(timezone.utc)
        for i in range(n):
            # stagger start_times so ordering is deterministic
            db_session.add(
                Span(
                    trace_id=f"tr-pg-{i:04d}",
                    name="test.span",
                    kind="llm.generation",
                    start_time=now + timedelta(seconds=i),
                    project_id=project_id,
                )
            )
        await db_session.flush()

    async def test_default_page_size_is_20_and_next_cursor_returned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Scenario: default page size is 20 and next_cursor is returned."""
        project_id = await _get_project_id(db_session)
        await self._insert_traces(25, db_session, project_id)

        resp = await client.get("/v1/traces", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 20
        assert data["next_cursor"] is not None

    async def test_cursor_returns_remaining_page(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Scenario: using next_cursor returns the remaining 5 traces."""
        project_id = await _get_project_id(db_session)
        await self._insert_traces(25, db_session, project_id)

        first = await client.get("/v1/traces", headers={"X-API-Key": "test-key"})
        cursor = first.json()["next_cursor"]
        assert cursor is not None

        second = await client.get(
            "/v1/traces",
            params={"cursor": cursor},
            headers={"X-API-Key": "test-key"},
        )
        assert second.status_code == 200
        data = second.json()
        assert len(data["traces"]) == 5
        assert data["next_cursor"] is None

    async def test_page_size_param_overrides_default(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Scenario: page_size parameter overrides the default."""
        project_id = await _get_project_id(db_session)
        await self._insert_traces(10, db_session, project_id)

        resp = await client.get(
            "/v1/traces",
            params={"page_size": 5},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["traces"]) == 5

    async def test_page_size_above_maximum_is_rejected(self, client: AsyncClient):
        """Scenario: page_size above maximum is rejected with 422."""
        resp = await client.get(
            "/v1/traces",
            params={"page_size": 500},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422

    async def test_invalid_cursor_returns_422(self, client: AsyncClient):
        """Scenario: invalid cursor value returns 422."""
        resp = await client.get(
            "/v1/traces",
            params={"cursor": "not-a-valid-cursor"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 422

    async def test_no_next_cursor_when_results_fit_in_one_page(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """next_cursor should be null when all results fit in the page."""
        project_id = await _get_project_id(db_session)
        await self._insert_traces(5, db_session, project_id)

        resp = await client.get("/v1/traces", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 5
        assert data["next_cursor"] is None

    async def test_cursor_pagination_covers_all_traces(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Iterating through all pages with cursor should yield exactly 25 unique traces."""
        project_id = await _get_project_id(db_session)
        await self._insert_traces(25, db_session, project_id)

        all_ids = []
        cursor = None
        for _ in range(10):  # safety bound
            params: dict = {"page_size": 10}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get(
                "/v1/traces", params=params, headers={"X-API-Key": "test-key"}
            )
            assert resp.status_code == 200
            page = resp.json()
            all_ids.extend(t["trace_id"] for t in page["traces"])
            cursor = page.get("next_cursor")
            if cursor is None:
                break

        assert len(all_ids) == 25
        assert len(set(all_ids)) == 25  # no duplicates
