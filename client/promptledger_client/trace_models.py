"""Pydantic models for the GET /v1/traces list endpoint — Story 5.3."""

from typing import List, Optional

from pydantic import BaseModel


class TraceListItem(BaseModel):
    """A single trace entry returned by GET /v1/traces."""

    trace_id: str
    status: str  # "ok" or "error"
    span_count: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost: Optional[float]
    start_time: Optional[str]


class TraceSummaryPage(BaseModel):
    """Paginated response from GET /v1/traces."""

    traces: List[TraceListItem]
    next_cursor: Optional[str]
