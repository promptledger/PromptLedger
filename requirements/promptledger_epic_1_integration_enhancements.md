# PromptLedger Epic 1: Integration Enhancements for Code-First, Multi-Provider Projects

**Target repo:** `PromptLedger` (separate project from ResearchKG)
**Motivation:** ResearchKG's Epic 22 integration exposed a set of PromptLedger gaps that make
Code-Based Tracking (Mode 2) unnecessarily hard to adopt for projects that (a) call Anthropic
directly instead of OpenAI, and (b) are developer-owned/Git-first. These enhancements should be
implemented in PromptLedger to benefit all future consuming projects, not just ResearchKG.

---

## Problem Statement

The integration guide and current API are OpenAI-centric and Mode 1-centric. Code-first teams
integrating against non-OpenAI providers face:

1. **No Anthropic provider** — Mode 1 execution (`/v1/executions:run`) only routes to OpenAI.
   Code-based teams are forced to stay in Mode 2 indefinitely, even when they would prefer the
   simpler Mode 1 path.

2. **No Python SDK** — every consuming project must hand-roll `httpx` calls, auth headers, retry
   logic, and span serialization. ResearchKG's `src/promptledger/client.py` is the third time
   this wheel has been reinvented.

3. **`register-code` is opaque** — there is no dry-run, no diff output, and no indication of
   whether a registration changed anything. Teams cannot validate their CI/CD registration step
   without side effects.

4. **Cost analytics are OpenAI-only** — token-cost calculations in `/v1/analytics/prompts` and
   `/v1/traces/{id}/summary` use OpenAI pricing tables. Anthropic spans logged via `/v1/spans`
   accumulate tokens but `total_cost` is always `$0.00`.

5. **Shallow Code-Based Tracking docs** — the integration guide dedicates one page to Mode 2
   and five pages to Mode 1. Teams choosing Code-Based Tracking have no canonical example for
   async `contextvars` trace propagation or injection-based tracker patterns.

---

## Stories

### Story 1.0 — API Key Authentication (Prerequisite)

**User Story:**
> As a **PromptLedger operator**, I want all API endpoints to require a valid `X-API-Key` header, so that unauthorized clients cannot read or modify prompts, executions, or traces in my deployment.

**Goal:** Replace the current stub `verify_api_key` with real middleware that enforces
`X-API-Key` authentication on all endpoints before anything is deployed to Railway.

**Why this is a prerequisite:**
The current `verify_api_key` function in `api/v1/endpoints/prompts.py` does nothing — every
request succeeds regardless of the header. All other Epic 1 stories assume working auth.
This must land first, before any story goes to production.

**Scope:**
- Add FastAPI middleware (or a `Depends` dependency applied at the router level) that:
  - Reads the `X-API-Key` header from every incoming request
  - Compares it against `settings.api_key` (constant-time comparison to prevent timing attacks)
  - Returns `401 Unauthorized` with `{"detail": "Invalid or missing API key"}` if absent or wrong
  - Allows requests to `GET /health` through without a key
- Remove the stub `verify_api_key` function from `prompts.py`
- Apply the dependency consistently across all v1 routers (prompts, code_prompts, executions,
  analytics, and the new spans router from Story 1.7)
- Add `API_KEY` validation note to `.env.example` — warn that the default value must be
  changed before production deployment

**Implementation note:** Use `secrets.compare_digest()` for the key comparison, not `==`.
This prevents timing-based key enumeration attacks.

**Tests (write first):**
- Request without `X-API-Key` header returns 401 on every protected endpoint
- Request with wrong key value returns 401
- Request with correct key succeeds
- `GET /health` returns 200 with no API key (health checks must not require auth)
- Constant-time comparison is used (verify `secrets.compare_digest` is called, not `==`)

---

### Story 1.1 — Anthropic Provider for Mode 1 Execution

**User Story:**
> As a **developer using Claude**, I want to execute prompts via `provider: "anthropic"` in the execution API, so that I can use PromptLedger's Mode 1 execution and lineage tracking without being forced onto OpenAI.

**Goal:** `/v1/executions:run` and `/v1/executions:submit` accept `provider: "anthropic"` and
route to the Anthropic Messages API using a caller-supplied `ANTHROPIC_API_KEY`.

**Implementation notes:**
The existing `ProviderAdapterFactory` in `services/providers.py` is already designed for this.
`_adapters` is a dict and `register_provider()` is a classmethod — adding `AnthropicAdapter`
is a drop-in extension with no changes to existing code. Follow the `OpenAIAdapter` pattern
exactly: implement `ProviderAdapter.generate()` and return the shared dict shape.

**Scope:**
- Add `AnthropicAdapter` class in `services/providers.py` alongside `OpenAIAdapter`
- Register it in `ProviderAdapterFactory._adapters` under key `"anthropic"`
- Add `anthropic>=0.40.0` to `pyproject.toml` dependencies (not optional — keep the dep
  unconditional so the import is always available; the API key is what's optional)
- Add `anthropic_api_key: str = Field(default="")` to `settings.py` (same pattern as
  `openai_api_key`); add `ANTHROPIC_API_KEY=` to `.env.example`
- Seed Anthropic models in `scripts/seed_models.py` alongside the existing OpenAI entries
- Support `model_name` values: `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`,
  `claude-opus-4-6` (and any future `claude-*` names via passthrough)
- Map `max_new_tokens` → Anthropic's `max_tokens`, `temperature` → `temperature` (direct)
- Map Anthropic `usage.input_tokens` / `usage.output_tokens` to the shared telemetry schema
  (`prompt_tokens` / `completion_tokens`) so downstream analytics and cost calculation work
  without provider-specific logic
- Populate `total_cost` using the pricing table introduced in Story 1.4

**Coupling note:** The `Span` model stores `model` (String) but not `provider`. Story 1.4's
cost model infers the provider from the model name via glob pattern matching — this is the
correct approach and avoids a schema migration. Stories 1.1 and 1.4 should be developed
together or in immediate sequence so the cost calculation is testable end-to-end.

**API change (backwards-compatible):**
```json
{
  "prompt_name": "extraction.paper",
  "variables": {"title": "...", "abstract": "..."},
  "model": {
    "provider": "anthropic",
    "model_name": "claude-haiku-4-5-20251001"
  }
}
```

**New env var (optional — only needed when `provider: "anthropic"` is used):**
```env
ANTHROPIC_API_KEY=sk-ant-...
```

**Tests (write first):**
- `AnthropicAdapter.generate()` returns `response_text`, `prompt_tokens`, `response_tokens`,
  `latency_ms`, `provider_request_id` (same keys as `OpenAIAdapter`)
- Anthropic `AuthenticationError` surfaces as 502 from PromptLedger (not 500)
- Anthropic `RateLimitError` surfaces as 429 from PromptLedger
- `model_name` with unknown `claude-*` prefix is passed through to the API unchanged
- Span created by a Mode 1 Anthropic execution has correct `prompt_tokens` / `completion_tokens`
- `total_cost` is non-zero for a known Anthropic model (requires Story 1.4 pricing table)
- Missing `ANTHROPIC_API_KEY` when `provider: "anthropic"` is requested returns a clear 400,
  not an unhandled exception

---

### Story 1.2 — Official Python Client SDK (`promptledger-client`)

**User Story:**
> As a **Python developer integrating PromptLedger**, I want a pip-installable `promptledger-client` package with async and sync clients, so that I can log spans, register prompts, and propagate trace IDs without writing boilerplate httpx code in every project.

**Goal:** Publish a pip-installable `promptledger-client` package that eliminates boilerplate
in every consuming project. Must support both sync and async usage.

**Package location decision: monorepo subdirectory.**
The SDK lives at `client/` within this repo (not a separate repository). This ensures the SDK
version is always developed and released in lockstep with the API it wraps, and CI can run
SDK tests against the local API in the same pipeline. The `client/` directory has its own
`pyproject.toml` and is published to PyPI as a separate package from that subdirectory.

**Directory layout:**
```
client/
  pyproject.toml       # package name: promptledger-client, version mirrors API
  promptledger_client/
    __init__.py        # exports PromptLedgerClient, AsyncPromptLedgerClient
    client.py          # sync httpx wrapper
    async_client.py    # async httpx wrapper
    models.py          # pydantic models: SpanPayload, RegistrationPayload, TraceRecord
    context.py         # contextvars helpers: start_trace(), current_trace_id(), etc.
    exceptions.py      # PromptLedgerError, AuthError, NotFoundError
  tests/
    test_async_client.py
    test_context.py
```

**`AsyncPromptLedgerClient` interface (minimum viable):**
```python
class AsyncPromptLedgerClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0): ...
    async def health(self) -> bool: ...
    async def register_code_prompts(self, prompts: list[RegistrationPayload]) -> RegisterResult: ...
    async def log_span(self, span: SpanPayload) -> str: ...          # returns span_id
    async def get_trace_summary(self, trace_id: str) -> TraceSummary: ...
```

**`context.py` (canonical implementation for consuming projects):**
```python
# Exactly the pattern from ResearchKG's Epic 22 — becomes the SDK default
start_trace() -> str
current_trace_id() -> str | None
current_parent_span_id() -> str | None
set_parent_span_id(span_id: str) -> None
```

**Packaging:**
- Published to PyPI as `promptledger-client` (PyPI account created ✓)
- `pip install promptledger-client` installs `httpx>=0.27`, `pydantic>=2`
- Drop the `[async]` extra — `httpx` includes async by default, the extra is a no-op and
  adds confusion
- Supports Python 3.11+
- SDK version is kept in sync with the API version (e.g. SDK `0.2.0` wraps API `0.2.x`)

**PyPI publishing pipeline — built as part of this story, first publish after epic is complete:**
- GitHub Actions workflow at `.github/workflows/publish-client.yml`
- Triggers on tags matching `client-v*` (e.g. `client-v0.2.0`)
- Builds from `client/` subdirectory, publishes to PyPI using a repository secret `PYPI_TOKEN`
- Run `twine check` before upload to catch malformed distributions
- **Action required before starting this story:** reserve the `promptledger-client` package
  name on PyPI by uploading a minimal stub release (`0.0.1`). Package names are first-come
  first-served — reserving it now prevents squatting. A stub `pyproject.toml` with an empty
  `__init__.py` is sufficient; the real package replaces it when the epic ships.
- The first real release (`0.1.0`) is tagged and published manually after all Epic 1 stories
  are merged and validated on Railway

**Tests (write first):**
- `AsyncPromptLedgerClient.health()` returns `True` on 200, `False` on any exception
- `log_span()` serializes `SpanPayload` correctly and returns `span_id` string
- `start_trace()` in one `asyncio.Task` does not leak into a sibling task (contextvars isolation)
- `register_code_prompts()` raises `AuthError` on 401, `PromptLedgerError` on 5xx
- `PromptLedgerClient` (sync) and `AsyncPromptLedgerClient` expose identical method signatures
  (sync client is a thin wrapper, not a separate implementation)

---

### Story 1.3 — `register-code` Dry-Run and Change Detection

**User Story:**
> As a **CI/CD pipeline**, I want to call `register-code` with `dry_run: true` and get back a per-prompt action report without writing to the database, so that I can validate prompt changes in a pull request without side effects.

**Goal:** `POST /v1/prompts/register-code` gains a `dry_run` flag and returns a per-prompt
`action` field indicating what would happen (or did happen).

**Request change:**
```json
{
  "prompts": [...],
  "dry_run": true
}
```

**Response change:**
```json
{
  "registered": 3,
  "updated": 2,
  "unchanged": 7,
  "dry_run": true,
  "details": [
    {"name": "extraction.paper",  "action": "update",    "hash_changed": true},
    {"name": "extraction.article","action": "unchanged", "hash_changed": false},
    {"name": "content.outline",   "action": "new",       "hash_changed": true}
  ]
}
```

**Rules:**
- `dry_run: true` → response is computed but **nothing is written to the database**
- `action: "unchanged"` when `template_hash` matches the stored active version
- `action: "update"` when hash differs from stored active version
- `action: "new"` when no record exists for this name
- Non-dry-run response uses the same `details` structure (enables CI diff reporting)

**Tests (write first):**
- Dry-run with unchanged prompt → `action: "unchanged"`, database record unchanged
- Dry-run with modified prompt → `action: "update"`, database record **not** updated
- Dry-run with new prompt → `action: "new"`, no database row created
- Live run with modified prompt → `action: "update"`, new version row created
- `registered` + `updated` + `unchanged` == total prompts submitted

---

### Story 1.4 — Multi-Provider Cost Model

**User Story:**
> As a **PromptLedger operator**, I want `total_cost` in trace summaries and analytics to reflect accurate Anthropic and OpenAI pricing, so that I can track LLM spend across providers without building my own cost calculation.

**Goal:** `total_cost` in trace summaries and analytics is calculated correctly for both
OpenAI and Anthropic models. Cost model is table-driven and updatable without code changes.

**Design decision: YAML-backed pricing table (not database-backed).**
A `pricing.yaml` file ships at the repo root and is loaded into memory at startup. Operators
can override it by mounting a custom file (Docker volume or Railway config). This avoids an
additional migration, an admin endpoint, and the operational complexity of keeping pricing
rows current in the database. If runtime price updates become a hard requirement in a future
epic, the in-memory loader can be swapped for a DB-backed loader without changing the
calculation logic.

**Design:**
- `pricing.yaml` at the repo root — loaded once at startup via a `PricingTable` helper class
- Rows: `(provider, model_pattern, input_cost_per_1k, output_cost_per_1k, effective_date)`
- `model_pattern` uses `fnmatch` glob matching so `claude-haiku-*` covers future haiku releases
- Provider is inferred from model name (e.g. `claude-*` → anthropic, `gpt-*` → openai) — no
  `provider` column needed on the `Span` model, avoiding a migration
- Cost calculation: `cost = (input_tokens/1000 * input_rate) + (output_tokens/1000 * output_rate)`
- Unrecognised model → `total_cost: null` (not `0.00`), so callers can distinguish
  "cost unknown" from "zero cost"

**Initial pricing table (as of 2026-03):**

| Provider | Model Pattern | Input $/1k | Output $/1k |
|---|---|---|---|
| anthropic | claude-haiku-4-5-* | 0.00080 | 0.00400 |
| anthropic | claude-sonnet-4-6* | 0.00300 | 0.01500 |
| anthropic | claude-opus-4-6* | 0.01500 | 0.07500 |
| openai | gpt-4o-mini* | 0.00015 | 0.00060 |
| openai | gpt-4o* | 0.00250 | 0.01000 |

**API change:** `GET /v1/traces/{trace_id}/summary` response gains:
```json
{
  "total_cost": 0.0023,
  "cost_breakdown": [
    {"span_name": "extraction.paper", "cost": 0.0015, "provider": "anthropic"},
    {"span_name": "newsletter_synthesis", "cost": 0.0008, "provider": "anthropic"}
  ]
}
```

**Tests (write first):**
- Known Anthropic model with known token counts produces correct `total_cost`
- Unknown model falls back to `null` cost rather than raising
- `gpt-4o-mini` glob matches `gpt-4o-mini-2024-07-18` (forward-compat)
- `claude-haiku-4-5-*` glob matches `claude-haiku-4-5-20251001`
- `GET /v1/traces/{id}/summary` returns `cost_breakdown` array with per-span costs

---

### Story 1.7 — Span Ingestion API (`/v1/spans` and `/v1/traces`)

**User Story:**
> As a **Mode 2 client application**, I want to POST spans to `/v1/spans` with agent identity and prompt linkage, so that PromptLedger can track the LLM calls I make directly and power cost analytics and multi-agent trace trees.

**Goal:** Give Mode 2 clients an HTTP endpoint to report the LLM calls they make directly,
so PromptLedger can record execution telemetry, correlate multi-step traces, and power
cost analytics — without owning the LLM call itself.

**Why this is its own story:**
The `Span` model and database table exist (FR-001), and spans are created internally for
Mode 1 executions. But there is no endpoint for external clients to push spans. Without this,
Mode 2 is version-tracking only — PromptLedger cannot observe any actual LLM calls made by
the client. This endpoint is also a hard prerequisite for Story 1.2 (the SDK's `log_span()`
method has nowhere to POST to) and for Story 1.4 (cost analytics requires spans with token
counts).

**Agent identity problem:**
In multi-agent workflows, several agents may make LLM calls within the same trace. The
existing `parent_span_id` tree can represent who called whom, but it gives no queryable
agent identity. Without an explicit agent field, the only options are name-prefix conventions
(`"researcher.extract"`) or stuffing agent data into the unindexed `attributes` JSONB —
neither supports clean per-agent analytics queries.

**Schema addition (one migration):**
Add `agent_id` (nullable `String(100)`, indexed) to the `spans` table:
```sql
ALTER TABLE spans ADD COLUMN agent_id TEXT;
CREATE INDEX idx_span_agent_id ON spans(agent_id);
```
No backfill needed — existing spans (Mode 1 internal) leave `agent_id` as `null`.

This makes agent identity first-class and filterable: average latency per agent, cost per
agent per trace, which agents ran in a given workflow, etc.

**New endpoints:**

`POST /v1/spans` — ingest one span from a client:
```json
{
  "trace_id": "trace-abc123",
  "parent_span_id": null,
  "agent_id": "researcher",
  "name": "extraction.paper",
  "kind": "llm.generation",
  "start_time": "2026-03-15T10:00:00.000Z",
  "end_time": "2026-03-15T10:00:01.250Z",
  "duration_ms": 1250,
  "status": "ok",
  "model": "claude-haiku-4-5-20251001",
  "prompt_tokens": 312,
  "completion_tokens": 87,
  "input_data": {"prompt_name": "extraction.paper"},
  "attributes": {"environment": "prod"}
}
```
Response: `{ "span_id": "<uuid>" }`

`GET /v1/traces/{trace_id}` — retrieve all spans belonging to a trace, ordered by
`start_time`. Returns the tree structure (parent/child relationships resolved), with
`agent_id` included on each span:
```json
{
  "trace_id": "trace-abc123",
  "span_count": 3,
  "start_time": "2026-03-15T10:00:00.000Z",
  "end_time": "2026-03-15T10:00:03.100Z",
  "duration_ms": 3100,
  "spans": [
    {
      "span_id": "...", "name": "extraction.paper",
      "agent_id": "researcher", "parent_span_id": null,
      "children": [...]
    }
  ]
}
```

`GET /v1/traces/{trace_id}/summary` — aggregated cost and token summary for a trace,
broken down by agent as well as by span (required by Story 1.4's cost model):
```json
{
  "trace_id": "trace-abc123",
  "span_count": 3,
  "total_prompt_tokens": 850,
  "total_completion_tokens": 210,
  "total_cost": 0.0023,
  "cost_breakdown": [
    {"span_name": "extraction.paper",   "agent_id": "researcher", "cost": 0.0015, "provider": "anthropic"},
    {"span_name": "newsletter_synthesis","agent_id": "writer",    "cost": 0.0008, "provider": "anthropic"}
  ],
  "by_agent": [
    {"agent_id": "researcher", "span_count": 2, "total_cost": 0.0015, "total_prompt_tokens": 620},
    {"agent_id": "writer",     "span_count": 1, "total_cost": 0.0008, "total_prompt_tokens": 230}
  ],
  "duration_ms": 3100
}
```

`GET /v1/analytics/agents` — cross-trace agent analytics (new analytics endpoint):
```json
{
  "agents": [
    {
      "agent_id": "researcher",
      "total_spans": 142,
      "total_cost": 1.24,
      "avg_latency_ms": 980,
      "avg_prompt_tokens": 410
    }
  ]
}
```

**Implementation notes:**
- New router: `src/prompt_ledger/api/v1/endpoints/spans.py`, registered under `/v1`
- New migration required: add `agent_id TEXT` column + index to `spans` table
- `POST /v1/spans` writes to the `spans` table with the new `agent_id` field
- `GET /v1/traces/{trace_id}` queries `WHERE trace_id = ?` and assembles the parent/child
  tree in Python (not recursive SQL) for simplicity at current scale
- `GET /v1/traces/{trace_id}/summary` computes `by_agent` by grouping spans on `agent_id`
  in Python after fetching; delegates cost per span to `PricingTable` from Story 1.4 —
  stub cost as `null` until 1.4 lands
- `GET /v1/analytics/agents` queries aggregate stats across all spans with a non-null
  `agent_id`, grouped by `agent_id` in SQL
- All endpoints require `X-API-Key` authentication (once auth middleware is real)

**Gap: Guardrail alert structure — use child spans, not `attributes`.**
Multi-agent workflows (e.g. the Synthetic Research Forum) have real-time guardrail checks
that produce structured alerts per turn: `alert_type`, `severity`, `description`,
`flagged_text`, `source_evidence`. Stuffing these into `attributes` JSONB loses queryability.

The canonical pattern is: **each guardrail evaluation is its own child span** under the
turn span it checked:
```
turn span (paper_1, kind="llm.generation")
  └── guardrail span (kind="guardrail.check", status="warning")
        attributes: {
          "alert_type": "grounding_violation",
          "severity": "WARNING",
          "flagged_text": "we achieved 94.2% on MMLU",
          "source_evidence": "Table 3 shows 91.8%"
        }
```
- Guardrail spans that find no violations: `status="ok"`
- Guardrail spans that find violations: `status="warning"` or `status="error"` (CRITICAL)
- `kind` for guardrail spans: `"guardrail.check"` (new canonical kind value)
- Multiple violations in one guardrail pass = multiple child spans, one per alert

This makes guardrail violations queryable via `GET /v1/analytics/agents?kind=guardrail.check`
and visible in the trace tree without special-casing. Document this pattern explicitly in
Story 1.6 docs.

**Gap: `prompt_name` linkage for Mode 2 spans.**
In Mode 2, the client calls the LLM directly — no `execution_id` links the span back to a
registered prompt. Without a prompt name on the span, analytics cannot answer "which prompt
version was active when this cost was incurred?" and version comparison across discussions
is impossible.

Add `prompt_name` as an optional, indexed field to the span payload:
```json
{ "prompt_name": "paper_agent_discussion", ... }
```
- Stored as an indexed `TEXT` column on `spans` (one additional migration line alongside
  `agent_id`)
- Not a FK — avoids coupling span ingestion to prompt registration; the name is advisory
- `GET /v1/analytics/prompts` (Mode 2 path) can group by `prompt_name` to show cost and
  latency per prompt template across all traces, even for client-executed calls

**Fields that are optional on ingest:**
`agent_id`, `prompt_name`, `parent_span_id`, `end_time`, `duration_ms` (client may not
know end time at submission), `prompt_tokens`, `completion_tokens`, `input_data`,
`output_data`, `attributes`, `model`.
`trace_id`, `name`, `kind`, `start_time`, `status` are required.

**Schema addition (update to migration for this story):**
```sql
ALTER TABLE spans ADD COLUMN agent_id     TEXT;
ALTER TABLE spans ADD COLUMN prompt_name  TEXT;
CREATE INDEX idx_span_agent_id    ON spans(agent_id);
CREATE INDEX idx_span_prompt_name ON spans(prompt_name);
```

**Tests (write first):**
- `POST /v1/spans` with valid payload returns 201 and a `span_id` UUID
- `POST /v1/spans` with `agent_id` stores it and returns it in subsequent GET responses
- `POST /v1/spans` with `prompt_name` stores it and returns it in subsequent GET responses
- `POST /v1/spans` without `agent_id` or `prompt_name` succeeds — both are optional
- `POST /v1/spans` with missing required field (`name`, `kind`, `trace_id`) returns 422
- `POST /v1/spans` with `kind="guardrail.check"` and `parent_span_id` creates a child span
  nested under the parent turn span in the tree response
- `GET /v1/traces/{trace_id}` returns all spans for that trace in tree order with `agent_id`
  and `prompt_name` included per span
- `GET /v1/traces/{trace_id}` for unknown `trace_id` returns 404
- Child span with `parent_span_id` appears nested under its parent in the tree response
- `GET /v1/traces/{trace_id}/summary` includes `by_agent` grouping when spans have `agent_id`
- `GET /v1/traces/{trace_id}/summary` `by_agent` is omitted (or empty) when no spans have `agent_id`
- Two spans with different `agent_id` values in the same trace appear in separate `by_agent` entries
- `GET /v1/traces/{trace_id}/summary` totals tokens correctly across all spans in the trace
- A span with no `model` field contributes `null` cost to the summary (not an error)
- `GET /v1/analytics/agents` returns aggregate stats only for spans with a non-null `agent_id`
- `GET /v1/analytics/agents?kind=guardrail.check` returns only guardrail spans, grouped by agent

---

### Story 1.6 — Code-Based Tracking Integration Guide (Documentation)

**User Story:**
> As a **developer evaluating PromptLedger for a code-first Anthropic project**, I want a complete Mode 2 integration guide with contextvars patterns, guardrail span examples, and CI dry-run recipes, so that I can integrate PromptLedger without reading source code or reverse-engineering other projects' implementations.

**Goal:** Replace the one-paragraph Mode 2 section in `INTEGRATION_GUIDE.md` with a full
worked example targeting non-OpenAI, code-first teams. This is a documentation-only story.

**Sections to add/expand:**

1. **When to choose Mode 2** — decision guide comparing Mode 1 vs Mode 2 with concrete
   trade-offs (not just a table). Explicitly call out: "if your LLM provider is not yet
   supported by PromptLedger's execution engine, Mode 2 is the right choice."

2. **End-to-end Mode 2 walkthrough** — complete Python example covering:
   - `pip install promptledger-client`
   - Startup registration using `AsyncPromptLedgerClient.register_code_prompts()`
   - Wrapping a direct Anthropic `messages.create()` call with timing + `log_span()`
   - Using `start_trace()` / `current_trace_id()` via `contextvars` for multi-step workflows
   - Injecting the client as `tracker=None` for test isolation

3. **CI/CD dry-run recipe** — GitHub Actions step showing how to use `dry_run: true` to
   assert no unregistered prompt changes slip into a release branch

4. **Graceful degradation pattern** — the "optional infrastructure" pattern where
   `PROMPTLEDGER_API_URL` absent → zero imports, all application code continues normally

5. **Async patterns** — `contextvars` isolation across `asyncio.Task` boundaries (the exact
   footgun that bites agentic/MCP applications)

6. **Stateless span-passing for workflow engines** — `contextvars` only survive within a
   single process and a single event loop iteration. Serverless environments (Railway
   sleeping, Celery tasks, Lobster workflow steps executing in separate invocations) cannot
   rely on in-memory context to carry `trace_id` or `parent_span_id` across steps.

   The canonical pattern for workflow engines is to pass span IDs explicitly through the
   workflow's state object, not through `contextvars`:
   ```python
   # At workflow start — store in workflow state, not contextvars
   state["trace_id"] = start_trace()
   state["phase_span_id"] = await client.log_span({
       "trace_id": state["trace_id"],
       "name": "open_discussion",
       "kind": "workflow.phase",
       "start_time": now(),
       "status": "ok",
   })

   # In each turn step — read from state, pass explicitly
   turn_span_id = await client.log_span({
       "trace_id": state["trace_id"],
       "parent_span_id": state["phase_span_id"],   # from state, not contextvars
       "agent_id": "paper_1",
       "prompt_name": "paper_agent_discussion",
       "kind": "llm.generation",
       ...
   })

   # Guardrail child span of the turn
   await client.log_span({
       "trace_id": state["trace_id"],
       "parent_span_id": turn_span_id,             # from the turn, not global state
       "agent_id": "guardrail",
       "kind": "guardrail.check",
       ...
   })
   ```
   Use `contextvars` only for in-process async fan-out (parallel tool calls within a single
   agent turn). Use explicit state passing for anything that crosses a process boundary,
   a sleep/wake cycle, or a workflow step transition.

7. **Guardrail alert pattern** — how to represent real-time grounding checks as child spans
   (kind="guardrail.check") under the turn spans they evaluate, including the `attributes`
   payload for `alert_type`, `severity`, `flagged_text`, and `source_evidence`. Reference
   the child span pattern documented in Story 1.7.

**Acceptance:** Both ResearchKG Epic 22 and the Synthetic Research Forum (SRF) Epic 1.5 can
be implemented by following the new guide without referencing any code outside
`promptledger-client` and the updated docs.

---

## Implementation Order

```
Phase 0 — prerequisite, must land before anything goes to production:
  1.0  API key auth           (stub middleware replaced with real enforcement)

Phase 1 — parallel, no inter-dependencies (two Claude instances can run these simultaneously):
  1.3  dry-run registration   (no new deps, self-contained service change)
  1.4  cost model             (pricing.yaml + PricingTable helper, no migration)
  1.1  Anthropic provider     (develop alongside 1.4 so cost calc is testable end-to-end)
  1.7  span ingestion API     (adds agent_id + prompt_name migration; stub cost as null
                               until 1.4 PricingTable is available)

Phase 2:
  1.2  Python SDK             (after 1.1, 1.3, 1.4, 1.7 — SDK models must reflect final API
                               shape; log_span() requires 1.7 endpoint to exist)

Phase 3:
  1.6  docs                   (after 1.1, 1.2, 1.7 complete; Mode 2 decision guide and
                               contextvars sections can be drafted in parallel earlier)
```

**Note:** Story 1.5 (project namespacing) has been deferred to Epic 2. Each consuming
project (SRF, ResearchKG) runs its own dedicated PromptLedger instance on Railway, providing
isolation without the complexity of in-instance namespacing.

---

## Backwards Compatibility Contract

Every story in this epic must preserve the following:

1. Existing `provider: "openai"` execution requests are unaffected
2. `register-code` without `dry_run` behaves exactly as today (new field is opt-in)
3. The existing `API_KEY` env var continues to work after Story 1.0 — real auth enforcement
   uses the same env var, just actually checks it now
4. `total_cost: null` (not `0.00`) for spans with unrecognized models — callers can
   distinguish "cost unknown" from "zero cost"
5. The `promptledger-client` SDK depends only on `httpx` and `pydantic` — no new
   transitive dependencies in consuming projects
6. Story 1.7's `agent_id` and `prompt_name` column additions to `spans` are both
   non-destructive: nullable with no backfill required; existing Mode 1 spans have
   both set to `null`

---

## Verification Checklist

```bash
# Story 1.0 — auth enforcement
curl $PL_URL/v1/prompts/my-prompt
# Expect: 401 Unauthorized (no key)
curl -H "X-API-Key: wrong" $PL_URL/v1/prompts/my-prompt
# Expect: 401 Unauthorized
curl -H "X-API-Key: $PL_KEY" $PL_URL/health
# Expect: 200 (no key required for health)

# Story 1.1 — Anthropic provider
curl -X POST $PL_URL/v1/executions:run \
  -H "X-API-Key: $PL_KEY" \
  -d '{"prompt_name":"extraction.paper","variables":{...},"model":{"provider":"anthropic","model_name":"claude-haiku-4-5-20251001"}}'
# Expect: response_text, telemetry.total_cost > 0

# Story 1.2 — SDK
pip install promptledger-client
python -c "from promptledger_client import AsyncPromptLedgerClient; print('ok')"

# Story 1.3 — dry-run
curl -X POST $PL_URL/v1/prompts/register-code \
  -d '{"prompts":[...],"dry_run":true}'
# Expect: details array with action fields, no DB write

# Story 1.4 — cost model
curl $PL_URL/v1/traces/$TRACE_ID/summary
# Expect: total_cost > 0 and cost_breakdown array when spans use Anthropic models

# Story 1.7 — span ingestion + agent identity
curl -X POST $PL_URL/v1/spans \
  -H "X-API-Key: $PL_KEY" \
  -d '{"trace_id":"trace-abc","agent_id":"researcher","name":"extraction.paper","kind":"llm.generation","start_time":"2026-03-15T10:00:00Z","status":"ok","model":"claude-haiku-4-5-20251001","prompt_tokens":312,"completion_tokens":87}'
# Expect: {"span_id": "<uuid>"}

curl $PL_URL/v1/traces/trace-abc/summary
# Expect: span_count, total tokens, by_agent array, total_cost (null until 1.4 lands)

curl $PL_URL/v1/analytics/agents
# Expect: per-agent aggregate stats across all traces

# Story 1.6 — docs
# Manual review: ResearchKG Epic 22 can be implemented end-to-end using only
# the updated integration guide + promptledger-client
```

---

## Context: Why These Enhancements Were Identified

ResearchKG (a Neo4j/Claude knowledge graph project) attempted PromptLedger integration in
Epic 22. Key findings:

- The project calls Claude directly (`anthropic` SDK), not OpenAI, so Mode 1 was unavailable.
  Mode 2 was chosen but required 150+ lines of hand-rolled client code that the SDK would replace.
- The `register-code` endpoint gave no feedback on what changed; a dry-run mode was needed
  for CI validation gates.
- Shared PromptLedger dev instances mixed prompts from multiple projects; namespacing was
  identified as a future need from day one.
- `total_cost` was always `$0.00` for all Anthropic spans, making analytics useless for
  the project's primary cost-visibility goal.

These are not ResearchKG-specific problems. Any engineering team using non-OpenAI providers
or sharing a PromptLedger instance will hit the same gaps.
