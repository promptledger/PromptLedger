# Epic 3: Async Execution Observability - Span Auto-Creation in the Celery Path

**Status:** Implemented on 2026-03-18
**Priority:** Completed - async and sync execution observability are now aligned

---

## Prerequisites

Epic 1 span ingestion and FR-003 sync auto-span creation must exist first. Epic 3 mirrors that sync behavior in the async Celery path.

---

## Context

Before this epic, `POST /v1/executions/submit` accepted a `span` block but did not use it. Async executions produced no span, returned no `span_id`, and were effectively invisible in trace views.

Epic 3 closed that gap:
- the submit endpoint now validates `span.trace_id` when a span block is present
- span context is forwarded into the Celery task payload
- the worker auto-creates the execution span after provider success
- the task result includes `span_id` when a span was created
- span write failures do not fail the execution itself

---

## Architecture Decisions

**Span context is passed as Celery task arguments.** Celery runs in a separate worker process, so the trace context must be serialized into the task payload.

**Span creation happens after provider completion.** This matches the sync path and ensures the span can include real token counts, latency, model name, and execution status.

**Span creation failure does not fail the task.** If the span write fails, the execution still succeeds and the task result returns `span_id = null`.

**Parent span IDs must reference a real span.** `spans.parent_span_id` is a foreign key to `spans.span_id`, so callers and tests must use an existing parent span ID rather than an arbitrary UUID.

---

## Stories

### Story 3.1 - Accept and Validate Span Block in Async Submit Endpoint

**Status:** Implemented

**Delivered:**
- `/v1/executions/submit` returns `202 Accepted`
- validates that `span.trace_id` is present when a `span` block is supplied
- forwards `span` into the Celery task arguments
- preserves `messages` and `span` in the tracked-prompt async path

**Files:**
- MODIFY: `src/prompt_ledger/api/v1/endpoints/executions.py`
- MODIFY: `src/prompt_ledger/api/v1/endpoints/code_prompts.py`

### Story 3.2 - Auto-Create Span Inside Celery Task

**Status:** Implemented

**Delivered:**
- added shared `build_execution_span(...)` helper in the execution service
- worker creates the async span after provider success
- span fields are populated from execution telemetry
- span writes are isolated so FK or flush failures do not poison the execution transaction

**Files:**
- MODIFY: `src/prompt_ledger/services/execution.py`
- MODIFY: `src/prompt_ledger/workers/tasks.py`

### Story 3.3 - Include `span_id` in Async Task Result

**Status:** Implemented

**Delivered:**
- worker task result now includes `span_id`
- returns `span_id = null` when no span context was supplied
- returns `span_id = null` when span creation fails

**Files:**
- MODIFY: `src/prompt_ledger/workers/tasks.py`

---

## Verification Checklist

```bash
pytest tests/integration/test_async_execution_observability.py -q
pytest tests/integration/test_executions_messages.py -q
```

**Executed on 2026-03-18:**
- `tests/integration/test_async_execution_observability.py` - `5 passed`
- `tests/integration/test_executions_messages.py` - `10 passed`
- Total targeted integration coverage - `15 passed`

---

## Critical Files

- MODIFY: `src/prompt_ledger/api/v1/endpoints/executions.py`
- MODIFY: `src/prompt_ledger/api/v1/endpoints/code_prompts.py`
- MODIFY: `src/prompt_ledger/services/execution.py`
- MODIFY: `src/prompt_ledger/workers/tasks.py`
- ADD: `tests/integration/test_async_execution_observability.py`
- MODIFY: `tests/integration/test_executions_messages.py`
- MODIFY: `README.md`
- MODIFY: `INTEGRATION_GUIDE.md`
- MODIFY: `ARCHITECTURE.md`
