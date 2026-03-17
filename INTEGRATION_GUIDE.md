# PromptLedger Integration Guide

**For Application Development Teams**

This guide covers both integration modes end-to-end, with particular depth on Mode 2
(Code-Based Tracking) for developer-owned, Git-first projects that call LLM providers
directly. Sections 4–10 are the canonical reference for any team using Anthropic or
another non-OpenAI provider.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start — Mode 1 (Full Management)](#quick-start--mode-1-full-management)
4. [When to Choose Mode 2 (Code-Based Tracking)](#when-to-choose-mode-2-code-based-tracking)
5. [End-to-End Mode 2 Walkthrough](#end-to-end-mode-2-walkthrough)
6. [CI/CD Dry-Run Recipe](#cicd-dry-run-recipe)
7. [Graceful Degradation Pattern](#graceful-degradation-pattern)
8. [Async Patterns — contextvars Isolation](#async-patterns--contextvars-isolation)
9. [Stateless Span-Passing for Workflow Engines](#stateless-span-passing-for-workflow-engines)
10. [Guardrail Alert Pattern](#guardrail-alert-pattern)
11. [API Reference Quick Guide](#api-reference-quick-guide)

---

## Overview

PromptLedger is an open-source prompt registry, execution, and lineage service. It solves
**prompt sprawl** by providing a centralized control plane for prompt versions, execution
tracking, and LLM call lineage.

**Two integration modes:**

| | Mode 1 — Full Management | Mode 2 — Code-Based Tracking |
|---|---|---|
| Prompts live in | PromptLedger database | Your application code / Git |
| LLM calls made by | PromptLedger execution engine | Your application |
| Provider support | OpenAI, Anthropic (Epic 1) | Any provider you can call |
| Best for | Non-technical editors, A/B tests | Developer-owned, Git-first projects |

---

## Prerequisites

- Python 3.11+
- A running PromptLedger instance (local Docker or Railway)
- `PROMPTLEDGER_API_URL` and `PROMPTLEDGER_API_KEY` environment variables

### Start PromptLedger locally

```bash
git clone https://github.com/your-org/promptledger
cd promptledger
cp .env.example .env          # set API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
make docker-up                # postgres + redis + api + worker
make migrate                  # alembic upgrade head
```

Health check:
```bash
curl http://localhost:8000/health
# → {"status": "healthy"}
```

---

## Quick Start — Mode 1 (Full Management)

Use Mode 1 when you want PromptLedger to own the LLM call. Prompts are stored in the
database and updates don't require code deployments.

### Install the SDK

```bash
pip install promptledger-client
```

### Configure environment

```env
PROMPTLEDGER_API_URL=http://localhost:8000
PROMPTLEDGER_API_KEY=your-api-key-here
```

### Create a prompt and execute it

```python
import asyncio
import os
from promptledger_client import AsyncPromptLedgerClient

async def main():
    client = AsyncPromptLedgerClient(
        base_url=os.environ["PROMPTLEDGER_API_URL"],
        api_key=os.environ["PROMPTLEDGER_API_KEY"],
    )

    # Create / update a prompt (idempotent — content-based versioning)
    import httpx
    async with httpx.AsyncClient() as http:
        await http.put(
            f"{os.environ['PROMPTLEDGER_API_URL']}/v1/prompts/doc_summarizer",
            headers={"X-API-Key": os.environ["PROMPTLEDGER_API_KEY"]},
            json={
                "description": "Summarize a document",
                "owner_team": "AI-Platform",
                "template_source": "Summarize the following:\n\n{{text}}",
                "created_by": "integration-guide",
                "set_active": True,
            },
        )

        # Synchronous execution (PromptLedger calls the LLM)
        response = await http.post(
            f"{os.environ['PROMPTLEDGER_API_URL']}/v1/executions:run",
            headers={"X-API-Key": os.environ["PROMPTLEDGER_API_KEY"]},
            json={
                "prompt_name": "doc_summarizer",
                "variables": {"text": "PromptLedger tracks prompt versions..."},
                "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                "params": {"max_new_tokens": 200, "temperature": 0.2},
            },
        )

    result = response.json()
    print(result["response_text"])
    print(f"Tokens: {result['telemetry']['prompt_tokens']} in / "
          f"{result['telemetry']['response_tokens']} out")
    print(f"Cost: ${result['telemetry']['total_cost']}")

asyncio.run(main())
```

---

## When to Choose Mode 2 (Code-Based Tracking)

### Decision guide

Choose **Mode 2** when any of the following is true:

- **Your LLM provider is not (yet) supported by PromptLedger's execution engine.**
  Mode 1's `/v1/executions:run` routes calls through PromptLedger's provider adapters.
  If you call a provider directly — a fine-tuned model behind your own endpoint, a
  local Ollama instance, or any provider without an adapter — Mode 2 is the right choice.
  You keep full control of the LLM call; PromptLedger observes it.

- **Your team is Git-first.** Prompts are code. They go through PR review, pass CI, and
  are deployed alongside the application that uses them. The database is the wrong home.

- **You want unit-testable prompts.** Templates defined as Python constants are trivially
  testable with no network calls. Mode 1 prompts require a running PromptLedger instance
  to render.

- **Prompt changes are infrequent and deliberate.** If your prompt template changes on
  every deploy (or less), the benefit of runtime editability doesn't justify the
  operational complexity of a database-managed prompt.

Choose **Mode 1** when:

- Non-engineers (product, marketing, support) need to edit prompts without a code deploy.
- You need A/B testing or canary deployments of prompt versions without redeploying code.
- You want PromptLedger to handle retry logic, async queuing, and provider failover.

### Trade-off summary

| | Mode 1 | Mode 2 |
|---|---|---|
| Provider flexibility | Adapters only | Any provider you can call |
| Prompt editability | Live, no deploy | Code deploy required |
| Unit testability | Network required | Trivial (`tracker=None`) |
| Observability setup | Automatic | ~20 lines per call site |
| CI validation | N/A | `dry_run: true` |
| Async fan-out control | Celery-managed | Your application's event loop |

---

## End-to-End Mode 2 Walkthrough

This section covers a complete Mode 2 integration using Anthropic as the LLM provider.
The same pattern works for any provider you call directly.

### 1. Install the SDK

```bash
pip install promptledger-client anthropic
```

### 2. Configure environment

```env
PROMPTLEDGER_API_URL=https://your-instance.up.railway.app
PROMPTLEDGER_API_KEY=your-api-key-here
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Define your prompts in code

```python
# my_app/prompts.py
PAPER_EXTRACTION = """\
You are a research assistant. Extract the key contributions from this paper.

Title: {{title}}
Abstract: {{abstract}}

Return a bullet list of the 3–5 most important contributions."""

NEWSLETTER_SYNTHESIS = """\
Synthesize the following research summaries into a newsletter section.

Summaries:
{{summaries}}

Write 2–3 paragraphs suitable for a technical newsletter."""
```

### 4. Register prompts at startup

```python
# my_app/startup.py
import os
from promptledger_client import AsyncPromptLedgerClient
from promptledger_client.models import RegistrationPayload
from my_app.prompts import PAPER_EXTRACTION, NEWSLETTER_SYNTHESIS


async def register_prompts(tracker: AsyncPromptLedgerClient | None = None) -> None:
    """Register code prompts with PromptLedger.

    Pass tracker=None in tests to skip registration entirely.
    """
    if tracker is None:
        return

    await tracker.register_code_prompts([
        RegistrationPayload(
            name="paper_agent.extraction",
            template_source=PAPER_EXTRACTION,
            description="Extract key contributions from a research paper",
            owner_team="ResearchKG",
        ),
        RegistrationPayload(
            name="paper_agent.synthesis",
            template_source=NEWSLETTER_SYNTHESIS,
            description="Synthesize research summaries into newsletter prose",
            owner_team="ResearchKG",
        ),
    ])
```

Call this from your application's startup sequence:

```python
# my_app/main.py
import os
import asyncio
from promptledger_client import AsyncPromptLedgerClient
from my_app.startup import register_prompts


async def lifespan():
    tracker = AsyncPromptLedgerClient(
        base_url=os.environ["PROMPTLEDGER_API_URL"],
        api_key=os.environ["PROMPTLEDGER_API_KEY"],
    )
    await register_prompts(tracker)
    # ... rest of startup
```

### 5. Wrap a direct Anthropic call with span logging

```python
# my_app/agents/researcher.py
import os
import time
from datetime import datetime, timezone

import anthropic
from promptledger_client import AsyncPromptLedgerClient
from promptledger_client.models import SpanPayload
from promptledger_client.context import current_trace_id, current_parent_span_id

from my_app.prompts import PAPER_EXTRACTION


async def extract_paper(
    title: str,
    abstract: str,
    tracker: AsyncPromptLedgerClient | None = None,
) -> str:
    """Extract key contributions from a paper and log the LLM call."""

    # Render the template
    rendered = PAPER_EXTRACTION.replace("{{title}}", title).replace(
        "{{abstract}}", abstract
    )

    # Call Anthropic directly
    client = anthropic.AsyncAnthropic()
    start = time.time()
    start_time = datetime.now(timezone.utc)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": rendered}],
    )

    duration_ms = int((time.time() - start) * 1000)
    result_text = response.content[0].text

    # Log the span to PromptLedger (no-op if tracker is None)
    if tracker is not None:
        span_id = await tracker.log_span(SpanPayload(
            trace_id=current_trace_id(),
            parent_span_id=current_parent_span_id(),
            name="paper_agent.extraction",
            kind="llm.generation",
            start_time=start_time.isoformat(),
            duration_ms=duration_ms,
            status="ok",
            model="claude-haiku-4-5-20251001",
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            prompt_name="paper_agent.extraction",
            input_data={"title": title, "abstract": abstract[:200]},
        ))

    return result_text
```

### 6. Multi-step workflows with contextvars trace propagation

```python
# my_app/workflows/research_pipeline.py
import asyncio
import os
from promptledger_client import AsyncPromptLedgerClient
from promptledger_client.context import start_trace, set_parent_span_id
from promptledger_client.models import SpanPayload
from my_app.agents.researcher import extract_paper
from my_app.agents.synthesizer import synthesize_newsletter


async def run_research_pipeline(
    papers: list[dict],
    tracker: AsyncPromptLedgerClient | None = None,
) -> str:
    """Run the full research pipeline for a batch of papers."""

    # Start a new trace for this pipeline run
    trace_id = start_trace()  # stored in a contextvar; visible to all coroutines below

    # Log a root span for the pipeline
    if tracker is not None:
        root_span_id = await tracker.log_span(SpanPayload(
            trace_id=trace_id,
            name="research_pipeline",
            kind="workflow.phase",
            start_time=_now(),
            status="ok",
        ))
        set_parent_span_id(root_span_id)  # child spans will nest under this

    # Extract contributions from all papers (sequential for simplicity)
    extractions = []
    for paper in papers:
        text = await extract_paper(
            title=paper["title"],
            abstract=paper["abstract"],
            tracker=tracker,
        )
        extractions.append(text)

    # Synthesize into newsletter prose
    newsletter = await synthesize_newsletter(
        summaries="\n\n".join(extractions),
        tracker=tracker,
    )

    return newsletter


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

### 7. Test isolation with `tracker=None`

The injection pattern makes testing trivial — pass `tracker=None` and no network calls
are made to PromptLedger:

```python
# tests/test_researcher.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from my_app.agents.researcher import extract_paper


async def test_extract_paper_no_tracker(monkeypatch):
    """extract_paper works correctly with tracker=None (no PromptLedger calls)."""

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Key contribution: ...")]
    mock_response.usage.input_tokens = 200
    mock_response.usage.output_tokens = 80

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda: mock_client)

    result = await extract_paper(
        title="Test Paper",
        abstract="This paper presents...",
        tracker=None,  # no PromptLedger calls
    )

    assert "Key contribution" in result
    mock_client.messages.create.assert_awaited_once()
```

---

## CI/CD Dry-Run Recipe

Use `dry_run: true` on `POST /v1/prompts/register-code` to assert that no unregistered
prompt changes have slipped into a release branch. The response reports what _would_
change without writing anything to the database.

### GitHub Actions step

```yaml
# .github/workflows/ci.yml

jobs:
  validate-prompts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install promptledger-client

      - name: Dry-run prompt registration
        env:
          PROMPTLEDGER_API_URL: ${{ secrets.PROMPTLEDGER_API_URL }}
          PROMPTLEDGER_API_KEY: ${{ secrets.PROMPTLEDGER_API_KEY }}
        run: python scripts/validate_prompts.py
```

```python
# scripts/validate_prompts.py
"""CI validation: assert no unregistered prompt changes in this branch."""

import asyncio
import os
import sys
import httpx
from my_app.prompts import PAPER_EXTRACTION, NEWSLETTER_SYNTHESIS
import hashlib


def checksum(template: str) -> str:
    return hashlib.sha256(template.encode()).hexdigest()


async def main() -> None:
    url = os.environ["PROMPTLEDGER_API_URL"]
    key = os.environ["PROMPTLEDGER_API_KEY"]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{url}/v1/prompts/register-code",
            headers={"X-API-Key": key},
            json={
                "prompts": [
                    {
                        "name": "paper_agent.extraction",
                        "template_source": PAPER_EXTRACTION,
                        "template_hash": checksum(PAPER_EXTRACTION),
                    },
                    {
                        "name": "paper_agent.synthesis",
                        "template_source": NEWSLETTER_SYNTHESIS,
                        "template_hash": checksum(NEWSLETTER_SYNTHESIS),
                    },
                ],
                "dry_run": True,  # nothing is written
            },
        )
        response.raise_for_status()

    data = response.json()
    assert data["dry_run"] is True

    changed = [d for d in data["details"] if d["action"] != "unchanged"]
    if changed:
        print("ERROR: The following prompts have uncommitted template changes:")
        for item in changed:
            print(f"  {item['name']}: {item['action']}")
        print()
        print("Register the updated prompts before merging to main:")
        print("  python scripts/register_prompts.py")
        sys.exit(1)

    print(f"OK: all {data['unchanged']} prompts are in sync with PromptLedger.")


asyncio.run(main())
```

**Dry-run response shape:**

```json
{
  "registered": 0,
  "updated": 1,
  "unchanged": 1,
  "dry_run": true,
  "details": [
    {"name": "paper_agent.extraction", "action": "update",     "hash_changed": true},
    {"name": "paper_agent.synthesis",  "action": "unchanged",  "hash_changed": false}
  ]
}
```

---

## Graceful Degradation Pattern

PromptLedger is observability infrastructure — your application must work even when it
is unreachable. The canonical pattern: if `PROMPTLEDGER_API_URL` is absent, skip all
SDK imports and continue normally.

```python
# my_app/observability.py
"""Optional PromptLedger integration.

If PROMPTLEDGER_API_URL is not set, this module exports a None tracker and
all call sites that check `if tracker is not None` are no-ops.
"""

import os
from typing import Optional

_url = os.environ.get("PROMPTLEDGER_API_URL")
_key = os.environ.get("PROMPTLEDGER_API_KEY")

tracker: Optional[object] = None

if _url and _key:
    # Only import the SDK when the service is actually configured.
    # This means the package does not need to be installed in environments
    # where PromptLedger is not used (e.g. local unit test runs).
    try:
        from promptledger_client import AsyncPromptLedgerClient

        tracker = AsyncPromptLedgerClient(base_url=_url, api_key=_key)
    except Exception as exc:  # import error, validation error, etc.
        import logging
        logging.getLogger(__name__).warning(
            "PromptLedger client failed to initialise — observability disabled: %s", exc
        )
```

Usage at every call site:

```python
from my_app.observability import tracker

result = await extract_paper(title=..., abstract=..., tracker=tracker)
# tracker is None → no PromptLedger calls, no import, no error
```

**Startup registration with graceful degradation:**

```python
# my_app/main.py
from my_app.observability import tracker
from my_app.startup import register_prompts

async def on_startup():
    await register_prompts(tracker)  # no-op when tracker is None
```

---

## Async Patterns — contextvars Isolation

### The footgun

`contextvars.ContextVar` values are **copied into child tasks at creation time** and do
not propagate back to the parent. This means that if one `asyncio.Task` calls
`start_trace()` or `set_parent_span_id()`, sibling tasks spawned afterwards will _not_
see those values unless they are passed explicitly.

This bites agentic and MCP applications that launch parallel tool calls from a single
agent turn:

```python
# ❌ WRONG — sibling tasks do NOT share contextvars
import asyncio
from promptledger_client.context import start_trace, current_trace_id

async def agent_turn():
    trace_id = start_trace()  # sets ContextVar in THIS task

    # These tasks are spawned AFTER start_trace().
    # Each gets a copy of the context at spawn time — that copy DOES include trace_id.
    # But changes made inside the child tasks (e.g. set_parent_span_id) do NOT
    # propagate back to the parent or to each other.
    results = await asyncio.gather(
        tool_search(query="..."),
        tool_lookup(key="..."),
    )
```

In the example above, `current_trace_id()` will return the correct value inside
`tool_search` and `tool_lookup` because they were spawned _after_ `start_trace()` set
the ContextVar. The trap is `set_parent_span_id()` — if you set a parent span ID inside
a child task, the parent task and sibling tasks will not see it.

### The correct pattern for parallel tool calls

Pass `parent_span_id` explicitly through function parameters for any span that needs
to nest under a specific parent:

```python
# ✅ CORRECT — parallel tool calls with explicit parent
import asyncio
from promptledger_client.context import start_trace, current_trace_id
from promptledger_client.models import SpanPayload


async def agent_turn(tracker):
    trace_id = start_trace()

    # Log the turn span first to get its ID
    if tracker:
        turn_span_id = await tracker.log_span(SpanPayload(
            trace_id=trace_id,
            name="agent_turn",
            kind="llm.generation",
            start_time=_now(),
            status="ok",
        ))
    else:
        turn_span_id = None

    # Pass turn_span_id explicitly — do NOT rely on contextvars for the children
    results = await asyncio.gather(
        tool_search(query="...", parent_span_id=turn_span_id, tracker=tracker),
        tool_lookup(key="...",   parent_span_id=turn_span_id, tracker=tracker),
    )
    return results


async def tool_search(query: str, parent_span_id: str | None, tracker):
    # ... do the search ...
    if tracker:
        await tracker.log_span(SpanPayload(
            trace_id=current_trace_id(),
            parent_span_id=parent_span_id,   # explicit, not from contextvar
            name="tool.search",
            kind="tool.call",
            start_time=_now(),
            status="ok",
        ))
```

### Summary rules

| Scenario | Use contextvars? |
|---|---|
| Sequential calls within a single async function | Yes — `current_trace_id()` works |
| Parallel `asyncio.gather()` — reading `trace_id` | Yes — copied at spawn time |
| Parallel `asyncio.gather()` — setting `parent_span_id` | No — pass explicitly |
| Across process/task boundaries (Celery, serverless) | No — see next section |

---

## Stateless Span-Passing for Workflow Engines

`contextvars` only survive within a single process and a single event loop iteration.
Serverless environments and workflow engines — Railway sleeping, Celery tasks, multi-step
workflow frameworks — execute steps in separate invocations and cannot rely on in-memory
context to carry `trace_id` or `parent_span_id` across steps.

**The canonical pattern: pass span IDs explicitly through the workflow state object.**

```python
# ✅ Workflow engine pattern — span IDs in state, not contextvars

async def start_discussion_phase(state: dict, tracker) -> dict:
    """Phase start: log a phase span and store its ID in state."""
    if tracker:
        state["trace_id"] = state.get("trace_id") or str(uuid.uuid4())
        state["phase_span_id"] = await tracker.log_span(SpanPayload(
            trace_id=state["trace_id"],
            name="open_discussion",
            kind="workflow.phase",
            start_time=_now(),
            status="ok",
        ))
    return state


async def run_agent_turn(
    state: dict,
    agent_id: str,
    message: str,
    tracker,
) -> dict:
    """Single agent turn: log a turn span nested under the phase span."""

    # Call the LLM
    response = await call_llm(agent_id=agent_id, message=message)

    if tracker:
        turn_span_id = await tracker.log_span(SpanPayload(
            trace_id=state["trace_id"],
            parent_span_id=state["phase_span_id"],   # from state, not contextvars
            agent_id=agent_id,
            name="paper_agent_discussion",
            kind="llm.generation",
            start_time=response.start_time,
            duration_ms=response.duration_ms,
            status="ok",
            model=response.model,
            prompt_tokens=response.input_tokens,
            completion_tokens=response.output_tokens,
            prompt_name="paper_agent_discussion",
        ))
        state["last_turn_span_id"] = turn_span_id

    state["messages"].append({"agent": agent_id, "content": response.text})
    return state
```

**Rule of thumb:**

- Use `contextvars` for in-process async fan-out (parallel tool calls within a single
  agent turn in a long-running server process).
- Use explicit state passing for anything that crosses a process boundary, a sleep/wake
  cycle, or a workflow step transition.

---

## Guardrail Alert Pattern

In multi-agent workflows, guardrail checks evaluate LLM outputs in real time.
The canonical PromptLedger pattern: **each guardrail evaluation is its own child span**
under the turn span it checked.

### Why child spans, not `attributes`

Stuffing alerts into a span's `attributes` JSONB field loses queryability.
Child spans are first-class: they appear in the trace tree, support filtering by `kind`,
and can be counted and aggregated across agents.

### Span structure

```
turn span  (paper_1, kind="llm.generation", status="ok")
  └── guardrail span  (kind="guardrail.check", status="warning")
        attributes: {
          "alert_type":      "grounding_violation",
          "severity":        "WARNING",
          "flagged_text":    "we achieved 94.2% on MMLU",
          "source_evidence": "Table 3 shows 91.8%"
        }
```

### Implementation

```python
async def run_guardrail_check(
    state: dict,
    turn_span_id: str,
    agent_id: str,
    response_text: str,
    source_context: str,
    tracker,
) -> list[dict]:
    """Run a grounding check and log the result as a child span."""

    alerts = await evaluate_grounding(response_text, source_context)

    if tracker:
        status = "ok" if not alerts else (
            "error" if any(a["severity"] == "CRITICAL" for a in alerts) else "warning"
        )

        if not alerts:
            # No violations — one span, status="ok", no alerts in attributes
            await tracker.log_span(SpanPayload(
                trace_id=state["trace_id"],
                parent_span_id=turn_span_id,
                agent_id=agent_id,
                name="guardrail.grounding",
                kind="guardrail.check",
                start_time=_now(),
                status="ok",
            ))
        else:
            # One child span per alert (queryable individually)
            for alert in alerts:
                await tracker.log_span(SpanPayload(
                    trace_id=state["trace_id"],
                    parent_span_id=turn_span_id,
                    agent_id=agent_id,
                    name="guardrail.grounding",
                    kind="guardrail.check",
                    start_time=_now(),
                    status=status,
                    attributes={
                        "alert_type":      alert["type"],
                        "severity":        alert["severity"],
                        "flagged_text":    alert.get("flagged_text", ""),
                        "source_evidence": alert.get("source_evidence", ""),
                    },
                ))

    return alerts
```

### Querying guardrail violations

```bash
# All guardrail spans across all agents (Story 1.7 analytics endpoint)
GET /v1/analytics/agents?kind=guardrail.check
```

```bash
# All spans for a specific trace (includes guardrail child spans in tree)
GET /v1/traces/{trace_id}
```

### `kind` values reference

| `kind` | When to use |
|---|---|
| `llm.generation` | Any LLM text generation call |
| `llm.embedding` | Embedding / vectorisation call |
| `tool.call` | External tool or API call |
| `tool.search` | Vector / full-text search |
| `workflow.phase` | A named phase or stage of a multi-step workflow |
| `guardrail.check` | A guardrail or safety evaluation (use child span pattern above) |

---

## API Reference Quick Guide

### Authentication

All `/v1/*` endpoints require:
```
X-API-Key: <your-api-key>
```

`GET /health` does **not** require authentication.

### Core endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check (no auth) |
| `PUT` | `/v1/prompts/{name}` | Create or update a prompt (Mode 1) |
| `GET` | `/v1/prompts/{name}` | Get prompt with active version |
| `GET` | `/v1/prompts/{name}/versions` | List all versions |
| `POST` | `/v1/executions:run` | Synchronous LLM execution (Mode 1) |
| `POST` | `/v1/executions:submit` | Async LLM execution (Mode 1) |
| `GET` | `/v1/executions/{id}` | Poll execution status |
| `POST` | `/v1/prompts/register-code` | Register code prompts (Mode 2) |
| `POST` | `/v1/spans` | Ingest a span from a client (Mode 2) |
| `GET` | `/v1/traces/{trace_id}` | Full trace tree with parent/child hierarchy |
| `GET` | `/v1/traces/{trace_id}/summary` | Aggregated cost and token summary |
| `GET` | `/v1/analytics/prompts` | Prompt execution analytics (both modes) |
| `GET` | `/v1/analytics/agents` | Cross-trace agent analytics |

### `POST /v1/executions:run` — synchronous execution response

```json
{
  "execution_id": "<uuid>",
  "status": "succeeded",
  "mode": "sync",
  "response_text": "...",
  "telemetry": {
    "prompt_tokens": 312,
    "response_tokens": 87,
    "latency_ms": 1240,
    "model_name": "claude-haiku-4-5-20251001",
    "provider": "anthropic",
    "total_cost": 0.00062
  }
}
```

`total_cost` is `null` (not `0.00`) when the model name is not in the pricing table.

### `POST /v1/executions:submit` — async submission response

```json
{
  "execution_id": "<uuid>",
  "status": "queued",
  "mode": "async",
  "model_name": "gpt-4o-mini",
  "provider": "openai"
}
```

Poll `GET /v1/executions/{execution_id}` for the full telemetry once the execution completes.

### `POST /v1/prompts/register-code`

```json
{
  "prompts": [
    {
      "name": "paper_agent.extraction",
      "template_source": "...",
      "template_hash": "<sha256>",
      "description": "...",
      "owner_team": "..."
    }
  ],
  "dry_run": false
}
```

Response:
```json
{
  "registered": 1,
  "updated": 0,
  "unchanged": 1,
  "dry_run": false,
  "details": [
    {"name": "paper_agent.extraction", "action": "new",       "hash_changed": true},
    {"name": "paper_agent.synthesis",  "action": "unchanged", "hash_changed": false}
  ]
}
```

### `POST /v1/spans`

Required fields: `trace_id`, `name`, `kind`, `start_time`, `status`

```json
{
  "trace_id": "trace-abc123",
  "parent_span_id": null,
  "agent_id": "researcher",
  "name": "paper_agent.extraction",
  "kind": "llm.generation",
  "start_time": "2026-03-17T10:00:00.000Z",
  "duration_ms": 1250,
  "status": "ok",
  "model": "claude-haiku-4-5-20251001",
  "prompt_tokens": 312,
  "completion_tokens": 87,
  "prompt_name": "paper_agent.extraction",
  "input_data": {"title": "..."},
  "attributes": {}
}
```

Response: `{"span_id": "<uuid>"}`

### `GET /v1/traces/{trace_id}/summary`

```json
{
  "trace_id": "trace-abc123",
  "span_count": 3,
  "total_prompt_tokens": 850,
  "total_completion_tokens": 210,
  "total_cost": 0.0023,
  "cost_breakdown": [
    {"span_name": "paper_agent.extraction", "cost": 0.0015, "provider": "anthropic"},
    {"span_name": "newsletter_synthesis",   "cost": 0.0008, "provider": "anthropic"}
  ],
  "duration_ms": 3100
}
```

`total_cost` is `null` (not `0.00`) when any span uses an unrecognised model name.

### `POST /v1/executions:run` — Mode 1 with Anthropic

```json
{
  "prompt_name": "doc_summarizer",
  "variables": {"text": "..."},
  "model": {
    "provider": "anthropic",
    "model_name": "claude-haiku-4-5-20251001"
  },
  "params": {
    "max_new_tokens": 512,
    "temperature": 0.2
  }
}
```

---

*Last updated: March 2026 — Epic 1 (Stories 1.0–1.4, 1.6)*
