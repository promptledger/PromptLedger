"""Story 1.1 — AnthropicAdapter unit tests.

TDD: confirm RED before implementing.
Uses unittest.mock to avoid real API calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAnthropicAdapter:
    """AnthropicAdapter must match the ProviderAdapter contract exactly."""

    def _make_mock_response(self, text="Hello", input_tokens=10, output_tokens=5):
        response = MagicMock()
        response.content = [MagicMock(text=text)]
        response.usage = MagicMock(
            input_tokens=input_tokens, output_tokens=output_tokens
        )
        response.id = "msg_test123"
        return response

    async def test_generate_returns_required_keys(self):
        from prompt_ledger.services.providers import AnthropicAdapter

        mock_response = self._make_mock_response("Test response", 20, 8)

        with patch("prompt_ledger.services.providers.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            adapter = AnthropicAdapter(api_key="sk-ant-test")
            result = await adapter.generate(
                rendered_prompt="Say hello",
                model_name="claude-haiku-4-5-20251001",
                params={},
            )

        assert result["response_text"] == "Test response"
        assert result["prompt_tokens"] == 20
        assert result["response_tokens"] == 8
        assert isinstance(result["latency_ms"], int)
        assert result["latency_ms"] >= 0
        assert result["provider_request_id"] == "msg_test123"

    async def test_maps_input_output_tokens_to_shared_schema(self):
        from prompt_ledger.services.providers import AnthropicAdapter

        mock_response = self._make_mock_response(input_tokens=412, output_tokens=198)

        with patch("prompt_ledger.services.providers.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            adapter = AnthropicAdapter(api_key="sk-ant-test")
            result = await adapter.generate("prompt", "claude-sonnet-4-6", {})

        assert result["prompt_tokens"] == 412
        assert result["response_tokens"] == 198

    async def test_missing_api_key_raises_value_error(self):
        from prompt_ledger.services.providers import AnthropicAdapter

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            AnthropicAdapter(api_key="")

    async def test_unknown_claude_model_passed_through(self):
        from prompt_ledger.services.providers import AnthropicAdapter

        mock_response = self._make_mock_response()

        with patch("prompt_ledger.services.providers.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            adapter = AnthropicAdapter(api_key="sk-ant-test")
            await adapter.generate("prompt", "claude-future-model-99", {})

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["model"] == "claude-future-model-99"

    async def test_max_tokens_param_mapped(self):
        from prompt_ledger.services.providers import AnthropicAdapter

        mock_response = self._make_mock_response()

        with patch("prompt_ledger.services.providers.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            adapter = AnthropicAdapter(api_key="sk-ant-test")
            await adapter.generate("prompt", "claude-sonnet-4-6", {"max_tokens": 500})

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["max_tokens"] == 500

    async def test_registered_in_factory(self):
        from prompt_ledger.services.providers import (
            AnthropicAdapter,
            ProviderAdapterFactory,
        )

        assert "anthropic" in ProviderAdapterFactory._adapters
        assert ProviderAdapterFactory._adapters["anthropic"] is AnthropicAdapter


class TestAnthropicAdapterErrorMapping:
    """API errors must surface as appropriate HTTP status codes."""

    async def test_authentication_error_raises_runtime_with_502_hint(self):
        from anthropic import AuthenticationError as AnthropicAuthError

        from prompt_ledger.services.providers import AnthropicAdapter

        mock_response = MagicMock()
        mock_response.status_code = 401
        auth_error = AnthropicAuthError(
            message="Invalid API key", response=mock_response, body={}
        )

        with patch("prompt_ledger.services.providers.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(side_effect=auth_error)
            mock_cls.return_value = mock_client

            adapter = AnthropicAdapter(api_key="sk-ant-bad")
            with pytest.raises(RuntimeError, match="502"):
                await adapter.generate("prompt", "claude-sonnet-4-6", {})

    async def test_rate_limit_error_raises_runtime_with_429_hint(self):
        from anthropic import RateLimitError as AnthropicRateLimitError

        from prompt_ledger.services.providers import AnthropicAdapter

        mock_response = MagicMock()
        mock_response.status_code = 429
        rate_error = AnthropicRateLimitError(
            message="Rate limit exceeded", response=mock_response, body={}
        )

        with patch("prompt_ledger.services.providers.AsyncAnthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(side_effect=rate_error)
            mock_cls.return_value = mock_client

            adapter = AnthropicAdapter(api_key="sk-ant-test")
            with pytest.raises(RuntimeError, match="429"):
                await adapter.generate("prompt", "claude-sonnet-4-6", {})
