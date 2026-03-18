"""Unit tests for SpanRequest Pydantic schema — Story 4.1.

TDD: written before schemas.py exists.
All tests should be RED until the schema is implemented.
"""

import pytest
from pydantic import ValidationError


class TestSpanRequestToolValidation:
    """Validate that kind='tool' gating is enforced by the Pydantic schema."""

    def test_tool_span_with_all_structured_fields_valid(self):
        from prompt_ledger.api.v1.schemas import SpanRequest

        req = SpanRequest(
            trace_id="trace-001",
            name="web_search",
            kind="tool",
            tool_name="web_search",
            tool_args={"query": "foo"},
            tool_result={"hits": [{"title": "Bar"}]},
            success=True,
            duration_ms=340,
        )
        assert req.tool_name == "web_search"
        assert req.success is True
        assert req.tool_args == {"query": "foo"}

    def test_tool_span_with_only_required_tool_fields_valid(self):
        from prompt_ledger.api.v1.schemas import SpanRequest

        req = SpanRequest(
            trace_id="trace-002",
            name="db_lookup",
            kind="tool",
            tool_name="db_lookup",
            success=False,
        )
        assert req.tool_name == "db_lookup"
        assert req.success is False
        assert req.tool_args is None
        assert req.tool_result is None

    def test_tool_span_without_tool_name_rejected(self):
        from prompt_ledger.api.v1.schemas import SpanRequest

        with pytest.raises(ValidationError) as exc_info:
            SpanRequest(
                trace_id="trace-003",
                name="web_search",
                kind="tool",
                # tool_name omitted
                success=True,
            )
        error_messages = str(exc_info.value)
        assert "tool_name required for kind=tool" in error_messages

    def test_non_tool_span_with_tool_name_rejected(self):
        from prompt_ledger.api.v1.schemas import SpanRequest

        with pytest.raises(ValidationError) as exc_info:
            SpanRequest(
                trace_id="trace-004",
                name="llm_call",
                kind="llm.generation",
                tool_name="web_search",  # invalid — not a tool span
            )
        error_messages = str(exc_info.value)
        assert "tool_name only valid for kind=tool" in error_messages

    def test_non_tool_span_without_tool_fields_valid(self):
        from prompt_ledger.api.v1.schemas import SpanRequest

        req = SpanRequest(
            trace_id="trace-005",
            name="llm_call",
            kind="llm.generation",
            model="claude-haiku-4-5-20251001",
            prompt_tokens=200,
            completion_tokens=80,
            duration_ms=1200,
        )
        assert req.tool_name is None
        assert req.success is None

    def test_tool_span_success_false_captures_error_message(self):
        from prompt_ledger.api.v1.schemas import SpanRequest

        req = SpanRequest(
            trace_id="trace-006",
            name="db_lookup",
            kind="tool",
            tool_name="db_lookup",
            success=False,
            status="error",
            error_message="connection timeout",
        )
        assert req.success is False
        assert req.status == "error"
        assert req.error_message == "connection timeout"
