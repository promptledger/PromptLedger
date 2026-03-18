"""Tests for AsyncPromptLedgerClient.execute() — FR-003.

TDD: written BEFORE the implementation exists.
All mocking uses unittest.mock to avoid extra test dependencies.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from promptledger_client.async_client import AsyncPromptLedgerClient
from promptledger_client.exceptions import NotFoundError, PromptLedgerError
from promptledger_client.execution import ExecutionResult, ExecutionTelemetry


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


MOCK_EXECUTION_RESPONSE = {
    "execution_id": "exec-uuid-123",
    "status": "succeeded",
    "mode": "sync",
    "response_text": "The debate conclusion is clear.",
    "span_id": None,
    "telemetry": {
        "prompt_tokens": 42,
        "response_tokens": 17,
        "latency_ms": 123,
        "model_name": "gpt-4o-mini",
        "provider": "openai",
        "total_cost": 0.0001,
    },
}


# ---------------------------------------------------------------------------
# execute() — messages input
# ---------------------------------------------------------------------------


class TestExecuteWithMessages:
    async def test_execute_with_messages_sends_correct_body(self, client):
        """execute() with messages sends messages in request body."""
        post_mock = AsyncMock(return_value=_mock_response(200, MOCK_EXECUTION_RESPONSE))
        with patch.object(client._http, "post", new=post_mock):
            messages = [{"role": "user", "content": "Hello!"}]
            await client.execute(
                "agent.debate_turn",
                messages=messages,
                model="gpt-4o-mini",
            )

        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert body["prompt_name"] == "agent.debate_turn"
        assert body["messages"] == messages
        assert "variables" not in body

    async def test_execute_with_messages_returns_execution_result(self, client):
        """execute() with messages returns ExecutionResult dataclass."""
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(return_value=_mock_response(200, MOCK_EXECUTION_RESPONSE)),
        ):
            result = await client.execute(
                "agent.debate_turn",
                messages=[{"role": "user", "content": "Hello!"}],
            )

        assert isinstance(result, ExecutionResult)
        assert result.execution_id == "exec-uuid-123"
        assert result.status == "succeeded"
        assert result.response_text == "The debate conclusion is clear."

    async def test_execute_telemetry_fields(self, client):
        """ExecutionResult.telemetry has correct fields."""
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(return_value=_mock_response(200, MOCK_EXECUTION_RESPONSE)),
        ):
            result = await client.execute(
                "agent.debate_turn",
                messages=[{"role": "user", "content": "Hello!"}],
            )

        assert isinstance(result.telemetry, ExecutionTelemetry)
        assert result.telemetry.prompt_tokens == 42
        assert result.telemetry.completion_tokens == 17
        assert result.telemetry.latency_ms == 123
        assert result.telemetry.model_name == "gpt-4o-mini"
        assert result.telemetry.provider == "openai"
        assert result.telemetry.total_cost == 0.0001


# ---------------------------------------------------------------------------
# execute() — variables input
# ---------------------------------------------------------------------------


class TestExecuteWithVariables:
    async def test_execute_with_variables_sends_correct_body(self, client):
        """execute() with variables sends variables in request body."""
        post_mock = AsyncMock(return_value=_mock_response(200, MOCK_EXECUTION_RESPONSE))
        with patch.object(client._http, "post", new=post_mock):
            await client.execute(
                "summarize.text",
                variables={"text": "Some text"},
                mode="mode1",
            )

        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert body["prompt_name"] == "summarize.text"
        assert body["variables"] == {"text": "Some text"}
        assert "messages" not in body


# ---------------------------------------------------------------------------
# execute() — state dict (span tracking)
# ---------------------------------------------------------------------------


class TestExecuteWithState:
    async def test_state_dict_adds_span_block(self, client):
        """state dict populates span block with trace_id."""
        post_mock = AsyncMock(return_value=_mock_response(200, MOCK_EXECUTION_RESPONSE))
        state = {"trace_id": "trace-abc-123", "phase_span_id": "span-parent-456"}
        with patch.object(client._http, "post", new=post_mock):
            await client.execute(
                "agent.step",
                messages=[{"role": "user", "content": "go"}],
                state=state,
            )

        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert "span" in body
        assert body["span"]["trace_id"] == "trace-abc-123"
        assert body["span"]["parent_span_id"] == "span-parent-456"

    async def test_state_dict_last_span_id_written_back(self, client):
        """state['last_span_id'] set to result.span_id after execution."""
        response_with_span = {**MOCK_EXECUTION_RESPONSE, "span_id": "new-span-999"}
        state = {"trace_id": "trace-abc-123"}
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(return_value=_mock_response(200, response_with_span)),
        ):
            result = await client.execute(
                "agent.step",
                messages=[{"role": "user", "content": "go"}],
                state=state,
            )

        assert result.span_id == "new-span-999"
        assert state["last_span_id"] == "new-span-999"

    async def test_no_state_no_span_block(self, client):
        """state=None → no span block in request body."""
        post_mock = AsyncMock(return_value=_mock_response(200, MOCK_EXECUTION_RESPONSE))
        with patch.object(client._http, "post", new=post_mock):
            result = await client.execute(
                "agent.step",
                messages=[{"role": "user", "content": "go"}],
                state=None,
            )

        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert "span" not in body
        assert result.span_id is None

    async def test_state_without_phase_span_id(self, client):
        """state without phase_span_id → no parent_span_id in span block."""
        post_mock = AsyncMock(return_value=_mock_response(200, MOCK_EXECUTION_RESPONSE))
        state = {"trace_id": "trace-xyz"}
        with patch.object(client._http, "post", new=post_mock):
            await client.execute(
                "agent.step",
                messages=[{"role": "user", "content": "go"}],
                state=state,
            )

        _, kwargs = post_mock.call_args
        body = kwargs["json"]
        assert "span" in body
        assert body["span"]["trace_id"] == "trace-xyz"
        assert "parent_span_id" not in body["span"]


# ---------------------------------------------------------------------------
# execute() — error handling
# ---------------------------------------------------------------------------


class TestExecuteErrorHandling:
    async def test_400_raises_promptledger_error(self, client):
        """400 response → PromptLedgerError raised."""
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(
                return_value=_mock_response(
                    400, {"detail": "messages not allowed for full-mode prompts"}
                )
            ),
        ):
            with pytest.raises(PromptLedgerError):
                await client.execute(
                    "full.summarize",
                    messages=[{"role": "user", "content": "bad request"}],
                )

    async def test_404_raises_not_found_error(self, client):
        """404 response → NotFoundError raised."""
        with patch.object(
            client._http,
            "post",
            new=AsyncMock(return_value=_mock_response(404)),
        ):
            with pytest.raises(NotFoundError):
                await client.execute(
                    "nonexistent.prompt",
                    messages=[{"role": "user", "content": "hello"}],
                )


# ---------------------------------------------------------------------------
# Importable from package root
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_execution_result_importable_from_root(self):
        """ExecutionResult importable from promptledger_client."""
        from promptledger_client import ExecutionResult  # noqa: F401

        assert ExecutionResult is not None

    def test_execution_telemetry_importable_from_root(self):
        """ExecutionTelemetry importable from promptledger_client."""
        from promptledger_client import ExecutionTelemetry  # noqa: F401

        assert ExecutionTelemetry is not None
