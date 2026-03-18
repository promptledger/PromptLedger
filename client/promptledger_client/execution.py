"""Execution result dataclasses for FR-003."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionTelemetry:
    """Telemetry data from a prompt execution."""

    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    model_name: str
    provider: str
    total_cost: Optional[float]


@dataclass
class ExecutionResult:
    """Result of a synchronous prompt execution."""

    execution_id: str
    status: str
    response_text: str
    span_id: Optional[str]
    telemetry: ExecutionTelemetry
