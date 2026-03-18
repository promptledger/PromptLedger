# promptledger-client

Python client SDK for [PromptLedger](https://github.com/promptledger/PromptLedger) — a prompt registry, execution tracking, and lineage service for GenAI applications.

`AsyncPromptLedgerClient(base_url, api_key)` expects the consuming application's
project-scoped API key. Do not use the PromptLedger deployment's admin/default-project key
for normal application traffic. See the main `README.md` for project creation and key
issuance via `/v1/admin/projects`.

## Installation

```bash
pip install promptledger-client
```

## Quick Start

```python
import os
from promptledger_client import AsyncPromptLedgerClient, RegistrationPayload

async def main():
    async with AsyncPromptLedgerClient(
        base_url=os.environ["PROMPTLEDGER_API_URL"],
        api_key=os.environ["PROMPTLEDGER_API_KEY"],
    ) as client:

        # 1. Register prompts at startup (idempotent)
        await client.register_code_prompts([
            RegistrationPayload(
                name="my_agent.turn",
                template_source="You are a research agent. {{instructions}}",
            )
        ])

        # 2. Execute — PL calls the LLM, logs the span, returns result + span_id
        state = {"trace_id": "my-run-001", "phase_span_id": "phase-abc"}

        result = await client.execute(
            prompt_name="my_agent.turn",
            messages=[
                {"role": "system", "content": "You are a research agent."},
                {"role": "user",   "content": "Summarise the key findings."},
            ],
            mode="mode2",
            state=state,       # reads trace_id/phase_span_id, writes last_span_id
            agent_id="researcher",
            max_tokens=512,
        )

        print(result.response_text)
        print(f"span_id: {result.span_id}")            # use as parent for child spans
        print(f"cost: ${result.telemetry.total_cost}")
        print(f"last_span_id: {state['last_span_id']}") # written back by execute()
```

## Core Methods

| Method | When to use |
|---|---|
| `execute()` | All LLM calls — Mode 1 and Mode 2. PL makes the LLM call, creates the span automatically, returns `response_text` + `span_id`. |
| `log_tool_call()` | Log a single tool invocation as a `kind='tool'` span. Handles payload construction; use `parent_span_id` to nest it under the current agent-turn span. |
| `register_code_prompts()` | At service startup to register or version-track prompt templates defined in code. Idempotent. |
| `log_span()` | Low-level span logging for non-LLM, non-tool steps: workflow phase spans, guardrail child spans. |
| `get_trace_summary()` | After a workflow run — retrieve aggregated token usage and cost for a full trace. |
| `health()` | Health check — returns `True` if the PromptLedger API is reachable. |

## `execute()` Reference

```python
result = await client.execute(
    prompt_name="my_agent.turn",   # required — links execution to registered prompt
    messages=[...],                # Mode 2: caller-constructed messages array
    variables={...},               # Mode 1: template variables (PL renders template)
    mode="mode2",                  # "mode1" or "mode2" (default: "mode2")
    state=state,                   # optional — reads/writes span IDs
    agent_id="researcher",         # optional — tagged on the auto-created span
    max_tokens=512,
    temperature=0.7,
)

# result.response_text: str
# result.span_id: str | None      — ID of the span created during execution
# result.execution_id: str
# result.telemetry.prompt_tokens: int
# result.telemetry.completion_tokens: int
# result.telemetry.latency_ms: int
# result.telemetry.total_cost: float | None
```

### `state` dict behaviour

If `state` is provided:
- `state["trace_id"]` → `span.trace_id`
- `state.get("phase_span_id")` → `span.parent_span_id`
- After execution: `state["last_span_id"] = result.span_id`

This eliminates manual span ID threading across Lobster workflow steps or any
stateless multi-step pipeline.

## Span Hierarchy Pattern

```python
from promptledger_client.models import SpanPayload

# Phase-level parent spans — use log_span() directly (no LLM call)
state["phase_span_id"] = await client.log_span(SpanPayload(
    trace_id=state["trace_id"],
    name="open_discussion",
    kind="workflow.phase",
    status="ok",
))

# Agent LLM turns — use execute() (PL makes LLM call, auto-creates span)
result = await client.execute(
    prompt_name="paper_agent_discussion",
    messages=[...],
    mode="mode2",
    state=state,   # parented under phase_span_id automatically
    agent_id="paper_1",
)

# Guardrail child spans — use log_span() with parent = the turn span
await client.log_span(SpanPayload(
    trace_id=state["trace_id"],
    parent_span_id=state["last_span_id"],  # child of the turn, not the phase
    agent_id="guardrail",
    name="guardrail_check",
    kind="guardrail.check",
    status="ok",
    attributes={"violations_found": 0},
))
```

## Context Helpers (single-process async only)

For simple in-process async workflows (not Lobster/Celery/serverless):

```python
from promptledger_client.context import start_trace, current_trace_id, set_parent_span_id
```

> **Warning:** Do not use contextvars across Lobster workflow steps, Celery tasks,
> or Railway sleeping cycles — they do not survive process boundaries.
> Use the `state` dict pattern with `execute()` instead.

## `log_tool_call()` Reference

```python
span_id = await client.log_tool_call(
    trace_id="my-run-001",
    tool_name="web_search",         # stable name — must match across all call sites
    tool_args={"query": "climate change"},
    tool_result={"hits": [...]},
    success=True,
    duration_ms=340,
    parent_span_id=state["last_span_id"],  # usually the current agent-turn span
    agent_id="researcher",
)
```

On failure:

```python
span_id = await client.log_tool_call(
    trace_id="my-run-001",
    tool_name="db_lookup",
    tool_args={"id": "doc-42"},
    tool_result={"error_type": "TimeoutError"},
    success=False,
    duration_ms=5000,
    error_message="connection timed out after 5 s",
    parent_span_id=state["last_span_id"],
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `trace_id` | `str` | yes | Current trace identifier |
| `tool_name` | `str` | yes | Stable tool name — used to aggregate analytics |
| `tool_args` | `dict` | yes | Arguments passed to the tool |
| `tool_result` | `dict` | yes | Return value / output from the tool |
| `success` | `bool` | yes | Whether the call succeeded |
| `duration_ms` | `int` | yes | Wall-clock duration of the tool call |
| `parent_span_id` | `str\|None` | no | ID of the parent span (usually the current agent-turn span) |
| `error_message` | `str\|None` | no | Human-readable error description when `success=False` |
| `agent_id` | `str\|None` | no | Agent identifier to attach to the span |

> **Note:** `parent_span_id` should normally be the span ID of the current
> agent-turn span (i.e., the most recent `result.span_id` returned by
> `execute()`). This places the tool call as a child of the turn that triggered it.

> **Note:** Use stable, consistent `tool_name` values across the codebase
> (`web_search`, `db_lookup`, `paper_fetch`, etc.) so that
> `GET /v1/analytics/tools` can aggregate error rates and latency correctly
> across all runs.

## Exceptions

| Exception | When raised |
|---|---|
| `AuthError` | 401 — invalid or missing API key |
| `NotFoundError` | 404 — prompt or trace not found |
| `PromptLedgerError` | 400, 422, 5xx — validation errors or server errors |
