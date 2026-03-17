"""Async HTTP client for the PromptLedger API."""

from typing import List

import httpx

from .exceptions import AuthError, NotFoundError, PromptLedgerError
from .models import RegisterResult, RegistrationPayload, SpanPayload, TraceSummary


class AsyncPromptLedgerClient:
    """Async client for the PromptLedger API.

    Usage::

        async with AsyncPromptLedgerClient(base_url="...", api_key="...") as client:
            span_id = await client.log_span(SpanPayload(...))
            summary = await client.get_trace_summary(trace_id)

    Or without context manager (remember to call ``await client.aclose()`` when done)::

        client = AsyncPromptLedgerClient(base_url="...", api_key="...")
        span_id = await client.log_span(...)
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def health(self) -> bool:
        """Return True if the API is reachable and healthy."""
        try:
            response = await self._http.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    async def log_span(self, span: SpanPayload) -> str:
        """Ingest a span and return the assigned span_id UUID string."""
        response = await self._http.post(
            "/v1/spans",
            json=span.model_dump(exclude_none=True),
        )
        self._raise_for_status(response)
        return response.json()["span_id"]

    async def register_code_prompts(
        self,
        prompts: List[RegistrationPayload],
        dry_run: bool = False,
    ) -> RegisterResult:
        """Register code-based prompts and return the action summary."""
        response = await self._http.post(
            "/v1/prompts/register-code",
            json={
                "prompts": [p.model_dump(exclude_none=True) for p in prompts],
                "dry_run": dry_run,
            },
        )
        self._raise_for_status(response)
        return RegisterResult(**response.json())

    async def get_trace_summary(self, trace_id: str) -> TraceSummary:
        """Fetch aggregated cost and token summary for a trace."""
        response = await self._http.get(f"/v1/traces/{trace_id}/summary")
        self._raise_for_status(response)
        return TraceSummary(**response.json())

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AsyncPromptLedgerClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise AuthError("Invalid or missing API key")
        if response.status_code == 404:
            raise NotFoundError("Resource not found")
        if response.status_code >= 500:
            raise PromptLedgerError(
                f"PromptLedger server error {response.status_code}: {response.text}"
            )
