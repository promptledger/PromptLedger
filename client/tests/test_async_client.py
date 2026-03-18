"""Tests for AsyncPromptLedgerClient — Story 1.2.

TDD: these tests are written before the implementation exists.
All mocking uses unittest.mock to avoid extra test dependencies.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from promptledger_client.async_client import AsyncPromptLedgerClient
from promptledger_client.exceptions import AuthError, NotFoundError, PromptLedgerError
from promptledger_client.models import RegistrationPayload, SpanPayload


@pytest.fixture
def client():
    return AsyncPromptLedgerClient(base_url="http://test.local", api_key="test-key")


def _mock_response(status_code: int, json_body=None, text: str = ""):
    """Build a fake httpx.Response-like mock."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body or {}
    mock.text = text
    return mock


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------


class TestHealth:
    async def test_returns_true_on_200(self, client):
        with patch.object(
            client._http, "get", new=AsyncMock(return_value=_mock_response(200))
        ):
            assert await client.health() is True

    async def test_returns_false_on_non_200(self, client):
        with patch.object(
            client._http, "get", new=AsyncMock(return_value=_mock_response(503))
        ):
            assert await client.health() is False

    async def test_returns_false_on_network_exception(self, client):
        with patch.object(
            client._http, "get", new=AsyncMock(side_effect=Exception("timeout"))
        ):
            assert await client.health() is False


# ---------------------------------------------------------------------------
# log_span()
# ---------------------------------------------------------------------------


class TestLogSpan:
    async def test_returns_span_id_on_201(self, client):
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(
                return_value=_mock_response(201, {"span_id": "abc-123-uuid"})
            ),
        ):
            span = SpanPayload(
                trace_id="trace-1", name="test.span", kind="llm.generation"
            )
            result = await client.log_span(span)
            assert result == "abc-123-uuid"

    async def test_serialises_span_fields(self, client):
        post_mock = AsyncMock(return_value=_mock_response(201, {"span_id": "xyz"}))
        with patch.object(client._http, "post", new=post_mock):
            span = SpanPayload(
                trace_id="t1",
                name="extraction.paper",
                kind="llm.generation",
                agent_id="researcher",
                prompt_name="paper_agent",
                model="claude-sonnet-4-6",
                prompt_tokens=412,
                completion_tokens=198,
                duration_ms=1340,
            )
            await client.log_span(span)

        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert body["trace_id"] == "t1"
        assert body["agent_id"] == "researcher"
        assert body["prompt_tokens"] == 412
        # None fields excluded
        assert "parent_span_id" not in body

    async def test_raises_auth_error_on_401(self, client):
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(return_value=_mock_response(401)),
        ):
            span = SpanPayload(trace_id="t", name="n", kind="k")
            with pytest.raises(AuthError):
                await client.log_span(span)

    async def test_raises_promptledger_error_on_5xx(self, client):
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(
                return_value=_mock_response(500, text="Internal Server Error")
            ),
        ):
            span = SpanPayload(trace_id="t", name="n", kind="k")
            with pytest.raises(PromptLedgerError):
                await client.log_span(span)


# ---------------------------------------------------------------------------
# register_code_prompts()
# ---------------------------------------------------------------------------


class TestRegisterCodePrompts:
    async def test_returns_register_result(self, client):
        body = {
            "registered": 2,
            "updated": 1,
            "unchanged": 0,
            "dry_run": False,
            "details": [],
        }
        with patch.object(
            client._http, "post", new=AsyncMock(return_value=_mock_response(200, body))
        ):
            prompts = [
                RegistrationPayload(name="p.one", template_source="Hello {{name}}"),
                RegistrationPayload(name="p.two", template_source="Goodbye {{name}}"),
            ]
            result = await client.register_code_prompts(prompts)
            assert result.registered == 2
            assert result.updated == 1
            assert result.dry_run is False

    async def test_dry_run_flag_sent_in_body(self, client):
        body = {
            "registered": 0,
            "updated": 0,
            "unchanged": 1,
            "dry_run": True,
            "details": [{"name": "p.one", "action": "unchanged"}],
        }
        post_mock = AsyncMock(return_value=_mock_response(200, body))
        with patch.object(client._http, "post", new=post_mock):
            await client.register_code_prompts(
                [RegistrationPayload(name="p.one", template_source="t")],
                dry_run=True,
            )
        _, kwargs = post_mock.call_args
        assert kwargs["json"]["dry_run"] is True

    async def test_raises_auth_error_on_401(self, client):
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(return_value=_mock_response(401)),
        ):
            with pytest.raises(AuthError):
                await client.register_code_prompts(
                    [RegistrationPayload(name="p", template_source="t")]
                )


# ---------------------------------------------------------------------------
# get_trace_summary()
# ---------------------------------------------------------------------------


class TestGetTraceSummary:
    async def test_returns_trace_summary(self, client):
        body = {
            "trace_id": "trace-abc",
            "span_count": 3,
            "total_prompt_tokens": 850,
            "total_completion_tokens": 210,
            "total_cost": 0.0023,
            "cost_breakdown": [],
            "by_agent": [],
            "duration_ms": 3100,
        }
        with patch.object(
            client._http, "get", new=AsyncMock(return_value=_mock_response(200, body))
        ):
            summary = await client.get_trace_summary("trace-abc")
            assert summary.trace_id == "trace-abc"
            assert summary.span_count == 3
            assert summary.total_cost == 0.0023

    async def test_raises_not_found_on_404(self, client):
        with patch.object(
            client._http,
            "get",
            new=AsyncMock(return_value=_mock_response(404)),
        ):
            with pytest.raises(NotFoundError):
                await client.get_trace_summary("no-such-trace")


# ---------------------------------------------------------------------------
# Sync client interface parity
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# log_tool_call()
# ---------------------------------------------------------------------------


class TestLogToolCall:
    async def test_log_tool_call_sends_correct_span_payload(self, client):
        post_mock = AsyncMock(
            return_value=_mock_response(201, {"span_id": "tool-span-xyz"})
        )
        with patch.object(client._http, "post", new=post_mock):
            result = await client.log_tool_call(
                trace_id="trace-abc",
                tool_name="web_search",
                tool_args={"query": "foo"},
                tool_result={"hits": []},
                success=True,
                duration_ms=340,
                parent_span_id="phase-span-xyz",
            )
        assert result == "tool-span-xyz"
        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert body["kind"] == "tool"
        assert body["tool_name"] == "web_search"
        assert body["success"] is True
        assert body["duration_ms"] == 340
        assert body["parent_span_id"] == "phase-span-xyz"
        assert body["trace_id"] == "trace-abc"

    async def test_log_tool_call_failure_sets_status_error(self, client):
        post_mock = AsyncMock(return_value=_mock_response(201, {"span_id": "err-span"}))
        with patch.object(client._http, "post", new=post_mock):
            await client.log_tool_call(
                trace_id="trace-fail",
                tool_name="db_lookup",
                tool_args={},
                tool_result={"error_type": "TimeoutError"},
                success=False,
                duration_ms=5000,
                error_message="timeout",
            )
        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert body["success"] is False
        assert body["status"] == "error"
        assert body["error_message"] == "timeout"

    async def test_log_tool_call_without_parent_span_id(self, client):
        post_mock = AsyncMock(
            return_value=_mock_response(201, {"span_id": "root-tool"})
        )
        with patch.object(client._http, "post", new=post_mock):
            await client.log_tool_call(
                trace_id="trace-root",
                tool_name="paper_fetch",
                tool_args={"doi": "10.1234/test"},
                tool_result={"abstract": "..."},
                success=True,
                duration_ms=210,
            )
        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert "parent_span_id" not in body

    async def test_log_tool_call_422_raises_promptledger_error(self, client):
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(
                return_value=_mock_response(422, {"detail": "tool_name required"})
            ),
        ):
            with pytest.raises(PromptLedgerError):
                await client.log_tool_call(
                    trace_id="t",
                    tool_name="x",
                    tool_args={},
                    tool_result={},
                    success=True,
                    duration_ms=1,
                )


class TestSyncClientParity:
    def test_sync_client_exposes_same_methods(self):
        from promptledger_client.client import PromptLedgerClient

        sync = PromptLedgerClient(base_url="http://x", api_key="k")
        for method in (
            "health",
            "log_span",
            "register_code_prompts",
            "get_trace_summary",
            "log_tool_call",
        ):
            assert callable(getattr(sync, method, None)), f"Missing method: {method}"
