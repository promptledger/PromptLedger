"""Pydantic models for PromptLedger client SDK requests and responses."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SpanPayload(BaseModel):
    """Payload for POST /v1/spans."""

    trace_id: str
    name: str
    kind: str
    status: str = "ok"
    parent_span_id: Optional[str] = None
    agent_id: Optional[str] = None
    prompt_name: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    attributes: Optional[Dict[str, Any]] = None


class RegistrationPayload(BaseModel):
    """A single prompt entry for POST /v1/prompts/register-code."""

    name: str
    template_source: str
    mode: str = "tracking"
    description: Optional[str] = None


class RegisterResult(BaseModel):
    """Response from POST /v1/prompts/register-code."""

    registered: int
    updated: int
    unchanged: int
    dry_run: bool
    details: List[Dict[str, Any]]


class TraceSummary(BaseModel):
    """Response from GET /v1/traces/{trace_id}/summary."""

    trace_id: str
    span_count: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost: Optional[float]
    cost_breakdown: List[Dict[str, Any]]
    by_agent: List[Dict[str, Any]]
    duration_ms: Optional[int]
