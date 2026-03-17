"""Sync wrapper around AsyncPromptLedgerClient.

This is a thin adapter — all logic lives in async_client.py.
Use this only when you cannot use async/await (e.g. in sync scripts or CLI tools).
In async contexts, use AsyncPromptLedgerClient directly.
"""

import asyncio
from typing import List

from .async_client import AsyncPromptLedgerClient
from .models import RegisterResult, RegistrationPayload, SpanPayload, TraceSummary


class PromptLedgerClient:
    """Synchronous client for the PromptLedger API.

    Wraps ``AsyncPromptLedgerClient`` via ``asyncio.run()``.
    Not suitable for use inside a running event loop — use
    ``AsyncPromptLedgerClient`` instead.

    Usage::

        client = PromptLedgerClient(base_url="...", api_key="...")
        span_id = client.log_span(SpanPayload(...))
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0) -> None:
        self._async = AsyncPromptLedgerClient(
            base_url=base_url, api_key=api_key, timeout=timeout
        )

    def health(self) -> bool:
        return asyncio.run(self._async.health())

    def log_span(self, span: SpanPayload) -> str:
        return asyncio.run(self._async.log_span(span))

    def register_code_prompts(
        self, prompts: List[RegistrationPayload], dry_run: bool = False
    ) -> RegisterResult:
        return asyncio.run(self._async.register_code_prompts(prompts, dry_run=dry_run))

    def get_trace_summary(self, trace_id: str) -> TraceSummary:
        return asyncio.run(self._async.get_trace_summary(trace_id))
