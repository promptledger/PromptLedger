"""promptledger-client — Python SDK for the PromptLedger API.

Quick start::

    from promptledger_client import AsyncPromptLedgerClient, SpanPayload
    from promptledger_client.context import start_trace

    client = AsyncPromptLedgerClient(base_url="https://...", api_key="...")
    trace_id = start_trace()
    span_id = await client.log_span(SpanPayload(
        trace_id=trace_id, name="extraction.paper",
        kind="llm.generation", model="claude-sonnet-4-6",
        prompt_tokens=412, completion_tokens=198,
    ))
"""

from .async_client import AsyncPromptLedgerClient
from .client import PromptLedgerClient
from .exceptions import AuthError, NotFoundError, PromptLedgerError
from .execution import ExecutionResult, ExecutionTelemetry
from .models import RegisterResult, RegistrationPayload, SpanPayload, TraceSummary
from .trace_models import TraceListItem, TraceSummaryPage

__version__ = "0.1.0"

__all__ = [
    "AsyncPromptLedgerClient",
    "PromptLedgerClient",
    "SpanPayload",
    "RegistrationPayload",
    "RegisterResult",
    "TraceSummary",
    "TraceListItem",
    "TraceSummaryPage",
    "PromptLedgerError",
    "AuthError",
    "NotFoundError",
    "ExecutionResult",
    "ExecutionTelemetry",
]
