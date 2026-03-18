"""Async HTTP client for the PromptLedger API."""

from typing import List, Optional

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

    async def execute(
        self,
        prompt_name: str,
        *,
        variables: Optional[dict] = None,
        messages: Optional[list] = None,
        mode: str = "mode2",
        model: Optional[str] = None,
        state: Optional[dict] = None,
        agent_id: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: Optional[float] = None,
    ) -> "ExecutionResult":
        """Execute a prompt synchronously and return an ExecutionResult.

        Args:
            prompt_name: Name of the registered prompt.
            variables: Template variables for full-mode prompts.
            messages: Pre-built messages list for tracking-mode prompts.
            mode: Execution mode (unused server-side; for SDK compatibility).
            model: Model name override (not currently used by server).
            state: Mutable state dict for span tracking. If provided, must have
                ``trace_id``. Optionally has ``phase_span_id`` which becomes
                ``parent_span_id``. After execution, ``last_span_id`` is written back.
            agent_id: Agent identifier to attach to the auto-span.
            max_tokens: Maximum tokens for the generation.
            temperature: Sampling temperature.

        Returns:
            ExecutionResult with response_text, telemetry and optional span_id.

        Raises:
            PromptLedgerError: On 400 or 5xx responses.
            NotFoundError: On 404 responses.
            AuthError: On 401 responses.
        """
        from .execution import ExecutionResult, ExecutionTelemetry

        body: dict = {
            "prompt_name": prompt_name,
            "mode": mode,
            "params": {"max_tokens": max_tokens},
        }

        if variables is not None:
            body["variables"] = variables
        if messages is not None:
            body["messages"] = messages
        if model is not None:
            body["model"] = model
        if temperature is not None:
            body["params"]["temperature"] = temperature
        if agent_id is not None:
            body.setdefault("span", {})["agent_id"] = agent_id

        if state is not None:
            span_block = body.setdefault("span", {})
            span_block["trace_id"] = state["trace_id"]
            if "phase_span_id" in state:
                span_block["parent_span_id"] = state["phase_span_id"]

        response = await self._http.post("/v1/executions/run", json=body)
        self._raise_for_status(response)
        data = response.json()

        tel = data.get("telemetry", {})
        result = ExecutionResult(
            execution_id=data["execution_id"],
            status=data["status"],
            response_text=data["response_text"],
            span_id=data.get("span_id"),
            telemetry=ExecutionTelemetry(
                prompt_tokens=tel.get("prompt_tokens", 0),
                completion_tokens=tel.get("response_tokens", 0),
                latency_ms=tel.get("latency_ms", 0),
                model_name=tel.get("model_name", ""),
                provider=tel.get("provider", ""),
                total_cost=tel.get("total_cost"),
            ),
        )

        if state is not None and result.span_id:
            state["last_span_id"] = result.span_id

        return result

    async def log_tool_call(
        self,
        *,
        trace_id: str,
        tool_name: str,
        tool_args: dict,
        tool_result: dict,
        success: bool,
        duration_ms: int,
        parent_span_id: Optional[str] = None,
        error_message: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """Log a tool call as a kind='tool' span and return the span_id.

        Constructs the span payload and posts it to POST /v1/spans.
        Sets status='error' automatically when success=False.

        Args:
            trace_id:       The current trace identifier.
            tool_name:      Stable name for the tool (e.g. 'web_search').
            tool_args:      Arguments passed to the tool.
            tool_result:    Return value / output from the tool.
            success:        Whether the tool call succeeded.
            duration_ms:    Wall-clock duration of the tool call.
            parent_span_id: ID of the parent span (usually the current agent turn).
            error_message:  Human-readable error description (for success=False).
            agent_id:       Agent identifier to attach to the span.

        Returns:
            The assigned span_id UUID string.

        Raises:
            PromptLedgerError: On 400, 422, or 5xx responses.
            AuthError:         On 401 responses.
        """
        body: dict = {
            "trace_id": trace_id,
            "name": tool_name,
            "kind": "tool",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_result": tool_result,
            "success": success,
            "duration_ms": duration_ms,
            "status": "error" if not success else "ok",
        }
        if parent_span_id is not None:
            body["parent_span_id"] = parent_span_id
        if error_message is not None:
            body["error_message"] = error_message
        if agent_id is not None:
            body["agent_id"] = agent_id

        response = await self._http.post("/v1/spans", json=body)
        self._raise_for_status(response)
        return response.json()["span_id"]

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
        if response.status_code in (400, 422):
            detail = response.json().get("detail", response.text)
            raise PromptLedgerError(f"Bad request: {detail}")
        if response.status_code == 401:
            raise AuthError("Invalid or missing API key")
        if response.status_code == 404:
            raise NotFoundError("Resource not found")
        if response.status_code >= 500:
            raise PromptLedgerError(
                f"PromptLedger server error {response.status_code}: {response.text}"
            )
