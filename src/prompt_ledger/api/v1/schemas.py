"""Pydantic request/response schemas for PromptLedger API v1."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, model_validator


class SpanRequest(BaseModel):
    """Request schema for POST /v1/spans.

    Enforces that tool_name (and related fields) are only present when
    kind == "tool".  Non-tool spans that include tool_name are rejected
    with a 422 to prevent schema confusion.
    """

    # Required
    trace_id: str
    name: str
    kind: str

    # Standard span fields
    status: str = "ok"
    parent_span_id: Optional[str] = None
    agent_id: Optional[str] = None
    prompt_name: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    attributes: Optional[Dict[str, Any]] = None

    # Tool call fields — only valid when kind == "tool"
    tool_name: Optional[str] = None
    success: Optional[bool] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_tool_fields(self) -> "SpanRequest":
        is_tool = self.kind == "tool"
        if is_tool and not self.tool_name:
            raise ValueError("tool_name required for kind=tool")
        if not is_tool and self.tool_name is not None:
            raise ValueError("tool_name only valid for kind=tool")
        return self
