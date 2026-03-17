"""Contextvars helpers for trace ID and parent span ID propagation.

These are task-local in asyncio — a value set in task A is NOT visible in a
sibling task B. Use explicit state passing across process/task boundaries
(Celery, workflow steps). Use contextvars only for in-process async fan-out.

Usage::

    from promptledger_client.context import (
        start_trace, current_trace_id,
        current_parent_span_id, set_parent_span_id,
    )

    trace_id = start_trace()           # sets contextvar for this task
    span_id = await client.log_span(...)
    set_parent_span_id(span_id)        # child spans will see this as parent
"""

import uuid
from contextvars import ContextVar
from typing import Optional

_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_parent_span_id_var: ContextVar[Optional[str]] = ContextVar(
    "parent_span_id", default=None
)


def start_trace() -> str:
    """Generate a new trace ID, store it in the current task's context, and return it."""
    trace_id = str(uuid.uuid4())
    _trace_id_var.set(trace_id)
    return trace_id


def current_trace_id() -> Optional[str]:
    """Return the trace ID for the current task, or None if not set."""
    return _trace_id_var.get()


def current_parent_span_id() -> Optional[str]:
    """Return the current parent span ID for the current task, or None if not set."""
    return _parent_span_id_var.get()


def set_parent_span_id(span_id: str) -> None:
    """Set the parent span ID for the current task's context."""
    _parent_span_id_var.set(span_id)
