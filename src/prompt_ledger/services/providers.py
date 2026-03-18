"""Provider adapters for different AI services."""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from anthropic import AsyncAnthropic
from anthropic import AuthenticationError as AnthropicAuthError
from anthropic import RateLimitError as AnthropicRateLimitError
from openai import AsyncOpenAI

from prompt_ledger.settings import settings


class ProviderAdapter(ABC):
    """Abstract base class for AI provider adapters."""

    @abstractmethod
    async def generate(
        self,
        rendered_prompt: Optional[str],
        model_name: str,
        params: Dict[str, Any],
        messages: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Generate response from AI provider.

        Args:
            rendered_prompt: The rendered prompt template (None when messages provided)
            model_name: Name of the model to use
            params: Generation parameters
            messages: Optional pre-built messages list (overrides rendered_prompt)

        Returns:
            Dictionary containing:
            - response_text: str
            - prompt_tokens: int | None
            - response_tokens: int | None
            - latency_ms: int
            - provider_request_id: str | None
        """
        pass


class OpenAIAdapter(ProviderAdapter):
    """OpenAI provider adapter."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)

    async def generate(
        self,
        rendered_prompt: Optional[str],
        model_name: str,
        params: Dict[str, Any],
        messages: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Generate response using OpenAI API."""

        start_time = time.time()

        final_messages = (
            messages
            if messages is not None
            else [{"role": "user", "content": rendered_prompt}]
        )

        # Prepare request parameters
        request_params = {
            "model": model_name,
            "messages": final_messages,
        }

        # Add optional parameters
        if "temperature" in params:
            request_params["temperature"] = params["temperature"]
        if "max_tokens" in params:
            request_params["max_tokens"] = params["max_tokens"]
        if "top_p" in params:
            request_params["top_p"] = params["top_p"]

        try:
            response = await self.client.chat.completions.create(**request_params)

            latency_ms = int((time.time() - start_time) * 1000)

            return {
                "response_text": response.choices[0].message.content,
                "prompt_tokens": response.usage.prompt_tokens
                if response.usage
                else None,
                "response_tokens": response.usage.completion_tokens
                if response.usage
                else None,
                "latency_ms": latency_ms,
                "provider_request_id": response.id,
            }

        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")


class AnthropicAdapter(ProviderAdapter):
    """Anthropic provider adapter."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        resolved_key = api_key or settings.anthropic_api_key
        if not resolved_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when provider is 'anthropic'"
            )
        self.client = AsyncAnthropic(api_key=resolved_key)

    async def generate(
        self,
        rendered_prompt: Optional[str],
        model_name: str,
        params: Dict[str, Any],
        messages: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Generate response using Anthropic Messages API."""
        start_time = time.time()

        final_messages = (
            messages
            if messages is not None
            else [{"role": "user", "content": rendered_prompt}]
        )

        request_params: Dict[str, Any] = {
            "model": model_name,
            "max_tokens": params.get("max_tokens", 1024),
            "messages": final_messages,
        }

        if "temperature" in params:
            request_params["temperature"] = params["temperature"]

        try:
            response = await self.client.messages.create(**request_params)
            latency_ms = int((time.time() - start_time) * 1000)

            return {
                "response_text": response.content[0].text,
                "prompt_tokens": response.usage.input_tokens,
                "response_tokens": response.usage.output_tokens,
                "latency_ms": latency_ms,
                "provider_request_id": response.id,
            }

        except AnthropicAuthError as e:
            raise RuntimeError(f"502: Anthropic authentication error: {e}")
        except AnthropicRateLimitError as e:
            raise RuntimeError(f"429: Anthropic rate limit exceeded: {e}")
        except Exception as e:
            raise RuntimeError(f"Anthropic API error: {e}")


class ProviderAdapterFactory:
    """Factory for creating provider adapters."""

    _adapters = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
    }

    @classmethod
    def get_provider(cls, provider_name: str) -> ProviderAdapter:
        """Get provider adapter by name."""

        if provider_name not in cls._adapters:
            raise ValueError(f"Unsupported provider: {provider_name}")

        adapter_class = cls._adapters[provider_name]
        return adapter_class()

    @classmethod
    def register_provider(cls, name: str, adapter_class: type[ProviderAdapter]) -> None:
        """Register a new provider adapter."""
        cls._adapters[name] = adapter_class
