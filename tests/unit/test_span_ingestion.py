"""Story 1.7 — Span ingestion unit tests.

Tests that don't require a database: tree assembly, cost calculation on spans.
TDD: confirm RED before implementing.
"""

from unittest.mock import MagicMock


class TestTraceTreeAssembly:
    """_build_trace_tree() assembles flat span list into parent/child tree."""

    def _make_span(self, span_id, parent_id=None, name="span", **kwargs):
        s = MagicMock()
        s.span_id = span_id
        s.parent_span_id = parent_id
        s.name = name
        s.kind = kwargs.get("kind", "llm.generation")
        s.agent_id = kwargs.get("agent_id", None)
        s.prompt_name = kwargs.get("prompt_name", None)
        s.status = kwargs.get("status", "ok")
        s.start_time = MagicMock()
        s.start_time.isoformat = lambda: "2026-03-16T00:00:00+00:00"
        s.end_time = None
        s.duration_ms = kwargs.get("duration_ms", None)
        s.model = kwargs.get("model", None)
        s.prompt_tokens = kwargs.get("prompt_tokens", None)
        s.completion_tokens = kwargs.get("completion_tokens", None)
        s.attributes = kwargs.get("attributes", None)
        return s

    def test_single_root_span(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_tree

        spans = [self._make_span("root-1", parent_id=None, name="root")]
        tree = _build_trace_tree(spans)
        assert len(tree) == 1
        assert tree[0]["name"] == "root"
        assert tree[0]["children"] == []

    def test_parent_child_relationship(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_tree

        parent = self._make_span("p1", parent_id=None, name="parent")
        child = self._make_span("c1", parent_id="p1", name="child")
        tree = _build_trace_tree([parent, child])
        assert len(tree) == 1
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["name"] == "child"

    def test_multiple_children(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_tree

        root = self._make_span("root", parent_id=None)
        c1 = self._make_span("c1", parent_id="root", name="child1")
        c2 = self._make_span("c2", parent_id="root", name="child2")
        tree = _build_trace_tree([root, c1, c2])
        assert len(tree[0]["children"]) == 2

    def test_nested_grandchild(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_tree

        root = self._make_span("root", parent_id=None)
        child = self._make_span("child", parent_id="root")
        grandchild = self._make_span("gc", parent_id="child", name="guardrail")
        tree = _build_trace_tree([root, child, grandchild])
        assert tree[0]["children"][0]["children"][0]["name"] == "guardrail"

    def test_agent_id_present_in_node(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_tree

        span = self._make_span("s1", parent_id=None, agent_id="paper_1")
        tree = _build_trace_tree([span])
        assert tree[0]["agent_id"] == "paper_1"

    def test_prompt_name_present_in_node(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_tree

        span = self._make_span("s1", parent_id=None, prompt_name="extraction.paper")
        tree = _build_trace_tree([span])
        assert tree[0]["prompt_name"] == "extraction.paper"


class TestTraceSummaryCalculation:
    """_build_trace_summary() aggregates cost and tokens across spans."""

    def _make_span(
        self,
        span_id,
        agent_id=None,
        model=None,
        prompt_tokens=None,
        completion_tokens=None,
        duration_ms=None,
        name="span",
    ):
        s = MagicMock()
        s.span_id = span_id
        s.name = name
        s.agent_id = agent_id
        s.model = model
        s.prompt_tokens = prompt_tokens
        s.completion_tokens = completion_tokens
        s.duration_ms = duration_ms
        s.start_time = MagicMock()
        s.start_time.isoformat = lambda: "2026-03-16T00:00:00+00:00"
        s.end_time = None
        return s

    def test_token_totals(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_summary
        from prompt_ledger.services.pricing import PricingTable

        pricing = PricingTable.default()
        spans = [
            self._make_span("s1", prompt_tokens=100, completion_tokens=50),
            self._make_span("s2", prompt_tokens=200, completion_tokens=80),
        ]
        summary = _build_trace_summary("t1", spans, pricing)
        assert summary["total_prompt_tokens"] == 300
        assert summary["total_completion_tokens"] == 130

    def test_known_model_produces_non_null_cost(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_summary
        from prompt_ledger.services.pricing import PricingTable

        pricing = PricingTable.default()
        spans = [
            self._make_span(
                "s1",
                model="claude-sonnet-4-6",
                prompt_tokens=1000,
                completion_tokens=500,
                agent_id="writer",
            )
        ]
        summary = _build_trace_summary("t1", spans, pricing)
        assert summary["total_cost"] is not None
        assert summary["total_cost"] > 0

    def test_unknown_model_cost_is_null(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_summary
        from prompt_ledger.services.pricing import PricingTable

        pricing = PricingTable.default()
        spans = [
            self._make_span(
                "s1", model="unknown-model-xyz", prompt_tokens=100, completion_tokens=50
            )
        ]
        summary = _build_trace_summary("t1", spans, pricing)
        assert summary["total_cost"] is None

    def test_by_agent_grouping(self):
        from prompt_ledger.api.v1.endpoints.spans import _build_trace_summary
        from prompt_ledger.services.pricing import PricingTable

        pricing = PricingTable.default()
        spans = [
            self._make_span(
                "s1",
                agent_id="researcher",
                model="claude-sonnet-4-6",
                prompt_tokens=400,
                completion_tokens=100,
            ),
            self._make_span(
                "s2",
                agent_id="writer",
                model="claude-sonnet-4-6",
                prompt_tokens=200,
                completion_tokens=80,
            ),
            self._make_span(
                "s3",
                agent_id="researcher",
                model="claude-sonnet-4-6",
                prompt_tokens=300,
                completion_tokens=90,
            ),
        ]
        summary = _build_trace_summary("t1", spans, pricing)
        by_agent = {row["agent_id"]: row for row in summary["by_agent"]}
        assert by_agent["researcher"]["span_count"] == 2
        assert by_agent["researcher"]["total_prompt_tokens"] == 700
        assert by_agent["writer"]["span_count"] == 1
