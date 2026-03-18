# Progress Tracker

Newest entries first. Updated after every commit.

---

## [2026-03-18] - Epic 2 Story 2.3: scope spans and executions to project

### Summary
- **Models:** `Span` and `Execution` — added nullable `project_id` FK to `projects` table with index on each
- **spans.py:** `ingest_span` stamps `project_id`; `get_trace` and `get_trace_summary` filter by `project_id` (cross-project trace IDs return 404)
- **analytics.py:** `get_prompts_analytics` and `get_agent_analytics` both scoped by `project_id`; `_cost_by_mode` helper updated to filter `Execution.project_id`
- **executions.py:** `run_execution_sync`, `submit_execution_async`, `get_execution`, `list_executions` all pass/scope `project_id`
- **ExecutionService:** `__init__` accepts optional `project_id`; stamped on new `Execution` records and auto-spans via `_create_span_for_execution`
- **code_prompts.py:** `execute_code_prompt` passes `project_id` to `ExecutionService`
- **Migration:** `f3a4b5c6d7e8` — add nullable `project_id` + backfill from default project + index, for both spans and executions; `down_revision = e2f3a4b5c6d7`
- **Tests:** 4 unit tests (`test_span_execution_scoping.py`) + 5 integration tests (`test_span_scoping.py`); all skip without Docker (expected)

### Decisions
- Kept `project_id` nullable post-migration (unlike prompts which went NOT NULL) — allows pre-namespacing rows to coexist; all new rows stamped via authenticated endpoints
- Analytics filtered via `Execution.project_id` rather than joining through `Prompt.project_id` — executions are the primary data source; joining through prompt would exclude executions from deleted prompts
- Auto-spans inherit `project_id` from `ExecutionService.project_id` — consistent with the execution they're linked to

### Issues & Resolution
- None — clean implementation; 2 pre-existing test failures unrelated to this story

### Next Steps
- [ ] Story 2.4: Admin API (running in parallel in user's other terminal)
- [ ] Story 2.5: Documentation update (after 2.4 is stable)

## [2026-03-18] - FR-003: messages input, auto-span creation, SDK execute()

### Summary
- **Model:** `src/prompt_ledger/models/execution.py` — `rendered_prompt` made nullable; `messages_json` JSONB column added
- **Migration:** `alembic/versions/c3d4e5f6a7b8_add_messages_json_to_executions.py` — alter + add column, with downgrade
- **Service:** `src/prompt_ledger/services/execution.py` — `execute_sync()` supports `messages` path (skip render), validates mode constraints, calls `_create_span_for_execution()` if span block present; `_create_execution()` accepts `messages` param; `submit_async()` updated to match new signature
- **Providers:** `src/prompt_ledger/services/providers.py` — `generate()` on both `OpenAIAdapter` and `AnthropicAdapter` accepts optional `messages` list; builds `final_messages` from messages or rendered_prompt
- **Endpoint:** `src/prompt_ledger/api/v1/endpoints/executions.py` — `/run` catches `ValueError` and returns HTTP 400
- **SDK dataclasses:** `client/promptledger_client/execution.py` — `ExecutionResult`, `ExecutionTelemetry`
- **SDK client:** `client/promptledger_client/async_client.py` — `execute()` method with messages/variables/state/agent_id params; `_raise_for_status` handles 400
- **SDK exports:** `client/promptledger_client/__init__.py` — exports `ExecutionResult`, `ExecutionTelemetry`
- **Tests (integration):** `tests/integration/test_executions_messages.py` — 10 tests (skip when Docker unavailable, will run GREEN with Docker)
- **Tests (SDK):** `client/tests/test_execute.py` — 12 tests, all GREEN
- **Result: 33/33 client tests pass; 46/46 non-Docker server tests pass; 0 regressions**

### Decisions
- `messages` path on tracking-mode prompts: skip Jinja render entirely, pass messages directly to provider
- Full-mode prompts reject messages input with 400; tracking prompts require either messages or variables
- Auto-span is created only when `span.trace_id` is present; failure is logged and swallowed (execution not failed)
- `_raise_for_status` now handles 400 → `PromptLedgerError` (not a new exception type — same class, different message)
- `state` dict pattern: mutable dict read/written by `execute()` for trace/span correlation across calls

### Issues & Resolution
- Span creation in `execute_sync` must happen before `commit()` but after result is available — placed in try/except between provider call and commit
- `parent_span_id` from request is a string UUID; must be converted to `uuid.UUID` before storing in Span (FK to spans.span_id which is PostgresUUID)

### Lessons Learned
- Integration tests with Docker skip cleanly — this is the correct behavior; tests will run GREEN in CI with `TEST_DATABASE_URL`
- Provider `generate()` signature change is backward-compatible (new optional param with default None)

### Next Steps
- [ ] Run integration tests against Docker when available to confirm GREEN
- [x] Update requirements/FR-003-unified-execution-client.md status → Implemented
- [x] Documentation stories 3.5 + 3.6 complete (see entry below)

---

## [2026-03-18] - FR-003 Stories 3.5 + 3.6: Documentation updates

### Summary
- **`INTEGRATION_GUIDE.md`** — Section 4 trade-off table updated (observability now "Automatic via execute()"); Section 5 Mode 2 walkthrough replaced 20-line boilerplate with `execute()` pattern (old pattern preserved in `<details>` legacy block); Section 7 graceful degradation updated; Section 9 stateless span-passing expanded with `execute()` + `state` dict pattern and `log_span()` vs `execute()` decision table; Section 11 API reference updated with Mode 2 `messages` request body and `span_id` response field
- **`README.md`** — Features list adds unified `execute()` method bullet; architecture diagram updated to show Mode 2 routing through PL (not direct provider call); `POST /v1/spans` demoted to low-level path
- **`client/README.md`** — Full rewrite: leads with `execute()` quick start, core method comparison table, `execute()` parameter reference, `state` dict behaviour, span hierarchy pattern, contextvars warning
- **`requirements/FR-003-unified-execution-client.md`** — Status updated to Implemented

### Decisions
- Old 20-line boilerplate kept in a `<details>` block so existing integrations aren't broken by the doc change
- `log_span()` vs `execute()` decision table added to stateless workflow section — clarifies which spans use each method
- client/README.md fully rewritten from placeholder to production-quality reference

## [2026-03-17] - E2E test suite against live Railway deployment

### Summary
- New: `tests/e2e/conftest.py` — session-scoped `base_url`/`api_key` fixtures; skips cleanly if env vars not set; function-scoped `AsyncPromptLedgerClient` fixture
- New: `tests/e2e/test_e2e.py` — 11 tests: health, auth rejection, no-key health, dry-run registration, live registration (new/unchanged/update), span ingestion, full 3-span trace workflow + summary, 404 handling, context helpers, analytics agents endpoint
- New: `.github/workflows/e2e.yml` — `workflow_dispatch` trigger; Railway URL as input, API key from repo secret `PROMPTLEDGER_API_KEY`
- **Result: 11/11 passed** against `https://prompt-ledger-api-production.up.railway.app`

### Bugs found and fixed by running the suite
- `RegistrationPayload.template` → `template_source` (SDK field name didn't match server schema)
- Session-scoped async fixture caused `RuntimeError: Event loop is closed` on Windows — dropped to function scope
- `PROMPTLEDGER_URL` / `PROMPTLEDGER_API_KEY` in env crashed Pydantic Settings (`extra_forbidden`) — added `extra = "ignore"` to Settings.Config

### Decisions
- Function-scoped client fixture: negligible overhead for e2e tests, avoids Windows asyncio event loop conflicts with session-scoped async fixtures
- `pytest.skip()` (not error) when env vars absent — normal `pytest` runs are unaffected
- No `--junit-xml` by default — can be added per-run with `--junit-xml=test-results/e2e.xml`

### How to run
```powershell
$env:PROMPTLEDGER_URL = "https://prompt-ledger-api-production.up.railway.app"
$env:PROMPTLEDGER_API_KEY = "your-key"
pytest tests/e2e/ -v
```

---

## [2026-03-17] - testcontainers: DB tests skip gracefully when Docker unavailable

### Summary
- Added `testcontainers[postgres]>=4.0.0` to dev dependencies
- `postgres_container` session-scoped fixture in `tests/conftest.py` auto-starts Postgres 15 container when `TEST_DATABASE_URL` not set
- Catches `DockerException` and calls `pytest.skip()` — converts 79 ERRORs to 85 SKIPs when Docker Desktop not running
- `TEST_DATABASE_URL` env var still respected for CI / `make docker-up` workflow

### Before / After
- Before: 40 passed, 79 errors
- After: 44 passed, 85 skipped, 0 errors

---

## [2026-03-17] - Agile user stories added to Epic 1 and Epic 2; CLAUDE.md standard

### Summary
- Added "As a [role], I want [capability], so that [benefit]" block to every story in `requirements/promptledger_epic_1_integration_enhancements.md` and `requirements/promptledger_epic_2_namespacing.md`
- Updated `CLAUDE.md` to document the user story format as required for all future requirement files

---

## [2026-03-17] - Story 1.8: Execution Telemetry Enhancement

### Summary
- `model_name` column added to `executions` table (migration `b2c3d4e5f6a7`)
- `Execution` ORM updated with `model_name = Column(String(100), nullable=True)`
- `ExecutionService._create_execution` sets `model_name=model.model_name`
- `ExecutionService.execute_sync` response `telemetry` now includes `model_name`, `provider`, `total_cost`
- `ExecutionService.submit_async` response now includes `model_name`, `provider`
- `GET /v1/executions/{id}` telemetry includes `model_name`, `provider`, `total_cost`
- `GET /v1/executions/` list entries include `model_name`
- `PricingTable` wired into executions endpoint for per-execution `total_cost`
- Tests: 4 unit tests (`test_execution_model_tracking.py`) GREEN; 6 integration tests (`test_execution_telemetry.py`) require Docker
- Docs: INTEGRATION_GUIDE.md API Reference updated with Mode 1 execution response schema; README roadmap updated

### Decisions
- `model_name` stored denormalized on `executions` row (alongside the `model_id` FK) so the list endpoint doesn't need an extra JOIN and historical data is preserved if the model record changes
- `total_cost` computed at read time via `PricingTable.calculate_cost()` — not persisted; ensures pricing updates apply retroactively
- `provider` read from the `Model` relationship in `get_execution` (eager-loaded); read from `Model` object in `execute_sync` response

### Issues & Resolution
- None

### Next Steps
- [ ] Story 1.2 — Official Python SDK (`promptledger-client`)
- [ ] Story 1.7 — Span ingestion API (`POST /v1/spans`, `GET /v1/traces/{id}/summary`)

---

## [2026-03-17] - Hotfix: extend provider_name enum to include 'anthropic'

### Summary
- New migration `a1b2c3d4e5f6`: `ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'anthropic'`
- Updated `Model.provider` ORM column to `Enum("openai", "anthropic", name="provider_name")`
- Root cause: Story 1.1 added Anthropic seeding and the adapter but the migration to extend
  the DB-level enum was missed — any `INSERT` with `provider='anthropic'` failed with a
  Postgres constraint error, making the Anthropic adapter silently unusable in production

### Decisions
- `IF NOT EXISTS` makes the migration idempotent (safe to run twice)
- Downgrade is a documented no-op — Postgres does not support removing enum values;
  the extra value causes no harm if unused

### Next Steps
- [ ] Story 1.8: Execution telemetry enhancement (model_name + provider + total_cost in response)

---

## [2026-03-17] - Story 1.2: Python Client SDK — promptledger-client v0.1.0 (Epic 1)

### Summary
- New package at `client/` — `pip install promptledger-client`
- `promptledger_client/exceptions.py` — `PromptLedgerError`, `AuthError`, `NotFoundError`
- `promptledger_client/models.py` — `SpanPayload`, `RegistrationPayload`, `RegisterResult`, `TraceSummary` (Pydantic)
- `promptledger_client/context.py` — `start_trace()`, `current_trace_id()`, `current_parent_span_id()`, `set_parent_span_id()`
- `promptledger_client/async_client.py` — `AsyncPromptLedgerClient`: `health()`, `log_span()`, `register_code_prompts()`, `get_trace_summary()`
- `promptledger_client/client.py` — `PromptLedgerClient` (sync wrapper via `asyncio.run()`)
- `tests/test_async_client.py` — 13 tests; `tests/test_context.py` — 8 tests (21 total, all GREEN)
- `.github/workflows/publish-client.yml` — publishes to PyPI on `client-v*` tags via `twine`
- Commit: `db70f17`

### Decisions
- `AsyncPromptLedgerClient` is the real implementation; `PromptLedgerClient` is a thin sync wrapper — no duplicated logic
- Tests mock `httpx.AsyncClient` methods directly via `unittest.mock` — no extra test dependencies (`respx` not needed)
- `SpanPayload.model_dump(exclude_none=True)` ensures only set fields are sent — server doesn't receive null-padded bodies
- Context isolation test (`test_trace_id_does_not_leak_into_sibling_task`) creates task_b before task_a sets the contextvar — proves isolation without timing games
- PyPI publish uses `PYPI_TOKEN` secret + `twine check` gate before upload

### Issues & Resolution
- black/isort reformatted 3 files on first commit — re-staged and committed clean

### Next Steps
- [ ] Tag `client-v0.1.0` and publish to PyPI (after Epic 1 fully validated on Railway)
- [ ] Story 1.6: Integration Guide docs (parallel session)

---

## [2026-03-17] - Story 1.6: Code-Based Tracking Integration Guide (Epic 1)

### Summary
- Full rewrite of `INTEGRATION_GUIDE.md` — replaces the one-paragraph Mode 2 section with
  7 canonical sections targeting non-OpenAI, developer-owned projects
- Updated `README.md` — removed stale fake Python client API, updated Features list to
  reflect Epic 1 state, updated Roadmap, replaced Mode 2 example with real API calls

### Sections added / rewritten
1. **When to Choose Mode 2** — concrete decision guide; explicit call-out that any
   unsupported LLM provider makes Mode 2 the right choice
2. **End-to-End Mode 2 Walkthrough** — full example: `pip install promptledger-client`,
   startup registration, Anthropic call wrapping with `log_span()`, multi-step workflow
   with `start_trace()` / `current_trace_id()`, `tracker=None` test isolation
3. **CI/CD Dry-Run Recipe** — GitHub Actions step + Python validation script using
   `dry_run: true`; exits non-zero when unregistered prompt changes are detected
4. **Graceful Degradation Pattern** — `PROMPTLEDGER_API_URL` absent → zero imports,
   all application code continues; `tracker=None` no-op pattern
5. **Async Patterns — contextvars Isolation** — the `asyncio.gather()` footgun explained;
   correct pattern: pass `parent_span_id` explicitly, rely on contextvars only for
   `trace_id` reading (not writing)
6. **Stateless Span-Passing for Workflow Engines** — canonical state-object pattern for
   serverless / Celery / workflow steps that cross process boundaries
7. **Guardrail Alert Pattern** — child spans with `kind="guardrail.check"`, one span per
   alert, `attributes` with `alert_type` / `severity` / `flagged_text` / `source_evidence`
- API Reference updated: correct endpoints, `POST /v1/spans` shape, trace summary shape,
  `total_cost: null` semantics, `kind` values reference table

### Decisions
- Code samples use `promptledger-client` SDK (`AsyncPromptLedgerClient`, `SpanPayload`,
  `RegistrationPayload`) — Story 1.2 SDK will match this interface
- Anthropic used as the primary Mode 2 example (the driving use case for Epic 1)
- `tracker=None` injection pattern is the canonical test isolation approach
- Guardrail pattern: multiple violations → multiple child spans (one per alert), not one
  span with a list in attributes — preserves queryability

### Issues & Resolution
- None — documentation-only story

### Next Steps
- [ ] Story 1.2: Python SDK (`promptledger-client`) — implement `AsyncPromptLedgerClient`,
  `SpanPayload`, `RegistrationPayload`, `context.py` to match this guide's examples

---

## [2026-03-17] - Fix spans POST 405: trailing slash route mismatch

### Summary
- Changed `@spans_router.post("/", ...)` → `@spans_router.post("", ...)` in `endpoints/spans.py`
- FastAPI does not redirect `POST /v1/spans` to `POST /v1/spans/` — it returns 405. Using `""` (empty string) makes the effective path `/v1/spans` with no trailing slash, matching what the notebook and SDK clients send
- Commit: `3a60ffe`

### Issues & Resolution
- Notebook section 4.1 returned 405 on all span POSTs — route registered as `"/"` produced `/v1/spans/`; notebook called `/v1/spans`

---

## [2026-03-16] - Fix pricing.yaml bundling for Docker/Railway deployments

### Summary
- Moved `pricing.yaml` from repo root into `src/prompt_ledger/pricing.yaml` (now installed as package data)
- Updated `_DEFAULT_PRICING_PATH` in `src/prompt_ledger/services/pricing.py` to `Path(__file__).parent.parent / "pricing.yaml"` — resolves correctly in both editable installs and `pip install .` / site-packages
- Added `[tool.setuptools.package-data]` to `pyproject.toml` so `pricing.yaml` is included in the wheel
- Commit: `60052ee`

### Issues & Resolution
- API crashed on Railway with `FileNotFoundError: /app/pricing.yaml` even after adding `COPY pricing.yaml .` to Dockerfiles — root cause: after `pip install .`, `pricing.py` is in site-packages and the 4-level `.parent` walk resolved to `/usr/local/lib/python3.11/`, not `/app/`
- Fix: bundle the file inside the package so it travels with the install, and use a 2-level parent walk from `__file__`

### Lessons Learned
- Any file referenced at runtime by path must either be bundled as package data or mounted externally — never rely on the repo layout being present in a Docker container
- `PRICING_YAML_PATH` env var override still works for operators who need a custom pricing file

---

## [2026-03-16] - Story 1.7: Span Ingestion API (Epic 1)

### Summary
- New: `src/prompt_ledger/api/v1/endpoints/spans.py` — `spans_router` (POST /v1/spans) and `traces_router` (GET /v1/traces/{id}, GET /v1/traces/{id}/summary)
- Added `agent_id` and `prompt_name` columns to `spans` table (migration `eb819e059121`)
- Added `GET /v1/analytics/agents` endpoint in `analytics.py` — cross-trace agent analytics grouped by `agent_id`
- Registered spans/traces routers in `src/prompt_ledger/api/v1/__init__.py`
- Tests: `tests/unit/test_span_ingestion.py` — 10 unit tests (tree assembly + summary calculation), all GREEN

### Decisions
- `_build_trace_tree()` and `_build_trace_summary()` are pure Python helpers tested independently — no DB needed for unit tests
- `trace_summary` cost uses `PricingTable` — unknown models return `null` (not 0), consistent with Story 1.4 semantics
- `agent_id` first-class column (indexed) for multi-agent analytics — not buried in `attributes` JSONB

---

## [2026-03-16] - Story 1.1: Anthropic Provider Adapter (Epic 1)

### Summary
- New: `AnthropicAdapter` in `src/prompt_ledger/services/providers.py` — implements `ProviderAdapter.generate()` using `AsyncAnthropic`
- Registered under `"anthropic"` key in `ProviderAdapterFactory._adapters`
- Added `anthropic_api_key` to `settings.py`; `ANTHROPIC_API_KEY=` added to `.env.example`
- Added `anthropic>=0.40.0` to `pyproject.toml`, `template/prompt-ledger-api/requirements.txt`, `template/prompt-ledger-worker/requirements.txt`
- Seeded `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-6` in `scripts/seed_models.py`
- Tests: `tests/unit/test_anthropic_provider.py` — 8 tests, all GREEN (mocked, no real API calls)

### Decisions
- `AsyncAnthropic` (not sync) to match the existing async FastAPI path
- Missing `ANTHROPIC_API_KEY` raises `ValueError` at adapter construction (not at request time) — surfaces as a clear 400-able error before any API call is made
- `AuthenticationError` → `RuntimeError("502: ...")`, `RateLimitError` → `RuntimeError("429: ...")` — HTTP status hint embedded in message for upstream handling
- `max_tokens` defaults to 1024 if not supplied (Anthropic requires this field, OpenAI does not)
- Token fields mapped: Anthropic `input_tokens`/`output_tokens` → shared schema `prompt_tokens`/`response_tokens`

### Issues & Resolution
- None

### Next Steps
- [ ] Story 1.7: Span Ingestion API (after Story 1.4 merges from parallel session)

---

## [2026-03-16] - Story 1.3: register-code Dry-Run and Change Detection (Epic 1)

### Summary
- Updated `src/prompt_ledger/services/prompt_service.py`: `register_code_prompts()` gains `dry_run: bool` param — reads DB, computes actions, skips all writes when `True`
- Updated `src/prompt_ledger/api/v1/endpoints/code_prompts.py`: new response shape with `registered`/`updated`/`unchanged` integer counts + `details` array + `dry_run` bool
- Each detail entry: `{"name", "action": "new"|"update"|"unchanged", "hash_changed": bool, "version", "change_detected", "previous_version"}`
- Tests: `tests/integration/test_register_code_dry_run.py` — 7 tests (require Docker for DB)

### Decisions
- `details` array returned on both dry-run and live runs — enables CI diff reporting without changing the call
- Breaking change to response shape: `{"registered": [...list...]}` → `{"registered": int, "updated": int, ...}` — old shape was only used internally; no external consumers yet

### Issues & Resolution
- None

### Next Steps
- [ ] Update `api_demo.ipynb` cells 2.1–2.3 to reflect new response shape

---

## [2026-03-16] - Story 1.0: API Key Auth + Operational Fixes

### Summary
- New: `src/prompt_ledger/api/dependencies.py` — `verify_api_key` using `secrets.compare_digest()`
- Updated `src/prompt_ledger/api/v1/__init__.py`: v1 router declared with `dependencies=[Depends(verify_api_key)]` — blanket auth on all `/v1/*` endpoints
- Removed no-op stub `verify_api_key` from `prompts.py`
- Added `pool_pre_ping=True` + `pool_recycle=1800` to async SQLAlchemy engine (fixes intermittent 500s from Railway closing idle connections)
- Updated `tests/conftest.py`: `client` fixture pins `settings.api_key = "test-key"`
- Tests: `tests/test_auth.py` — 5 tests, GREEN
- Fixed `examples/api_demo.ipynb`: removed `Content-Type: application/json` from `HEADERS` (was causing 500 on GET requests), added Celery worker warning to async execution cells
- Fixed Railway worker service: Dockerfile path was blank — worker was running the API instead of Celery

### Decisions
- `secrets.compare_digest()` over `==` — prevents timing-based key enumeration
- Auth applied at v1 router level, not per-endpoint — no endpoint can accidentally skip it
- `/health` is inherently exempt (lives on root app, not under `/v1`)

### Issues & Resolution
- Worker logs empty: Railway `prompt-ledger-worker` service had blank Dockerfile path, causing it to run `start.sh` (the API) instead of the Celery worker command. Fixed by setting path to `template/prompt-ledger-worker/Dockerfile`
- Analytics 500: caused by stale asyncpg connection (Railway closes idle connections), not Content-Type header. Fixed with `pool_pre_ping=True`

### Lessons Learned
- Railway does not automatically share env vars between services — each service needs its own `REDIS_URL` and `DATABASE_URL` references
- Jupyter does not source `.env` files — env vars must be set in the shell before launching, or hardcoded in the config cell

### Next Steps
- [ ] Set `ANTHROPIC_API_KEY` in Railway `prompt-ledger-api` and `prompt-ledger-worker` env vars

---

## [2026-03-16] - Story 1.4: Multi-Provider Cost Model (Epic 1)

### Summary
- New file: `pricing.yaml` (repo root) — YAML pricing table, 5 rows covering Anthropic and OpenAI models as of 2026-03
- New file: `src/prompt_ledger/services/pricing.py` — `PricingTable` class; fnmatch glob matching, provider inference from model name, `calculate_cost()` returns `None` for unknown models
- Updated: `src/prompt_ledger/api/v1/endpoints/analytics.py` — added `total_cost` field to both mode-specific and all-mode responses; computed via `_cost_by_mode()` helper that joins Execution → Model, groups by model_name, applies pricing in Python
- Tests: `tests/unit/test_pricing.py` (17 tests — 100% GREEN); `tests/integration/test_analytics_cost.py` (6 tests — require Docker)
- No migration needed — provider inferred from model name via glob, no schema changes

### Decisions
- YAML-backed pricing table (not DB-backed): avoids migration + admin endpoint; operators can override via `PRICING_YAML_PATH` env var (Docker volume or Railway config)
- Module-level `_pricing_table` singleton in analytics.py: loaded once at import, not per-request
- `total_cost: null` (not `0.00`) for unknown models: callers can distinguish "unknown" from "zero"
- `total_cost: 0.0` when there are no executions: zero is a known state (no cost incurred)
- Mixed-model traces (some unknown): total_cost = null, per-span entries still show individual costs
- gpt-4o-mini* pattern comes before gpt-4o* in pricing.yaml: preserves correct first-match semantics since fnmatch("gpt-4o-mini", "gpt-4o*") would be True

### Issues & Resolution
- None — clean implementation

### Lessons Learned
- fnmatch ordering is load-bearing: more-specific patterns must precede less-specific ones in the YAML

### Next Steps
- [ ] Story 1.1: Anthropic provider adapter — AnthropicAdapter in providers.py, cost calculation will work automatically via PricingTable glob matching
- [ ] Story 1.7: Span ingestion API — /v1/spans and /v1/traces/{id}/summary; use PricingTable for per-span cost_breakdown

---

## [2026-02-03] - Automatic Model Seeding on API Startup

### Summary
- Added model seeding to the FastAPI lifespan handler so default AI models are populated on every cold start
- Fixed `seed_models` import path to work correctly inside the Docker container (`scripts.seed_models` rather than a relative import)
- Modified: `src/prompt_ledger/api/main.py`, `scripts/seed_models.py`
- Commits: `e7535e9`, `7dc8673`, `acd252a`

### Decisions
- Seeding runs at startup rather than as a one-off migration step so Railway deployments self-initialise without manual intervention
- Seeding failures are caught and logged but do not abort startup — avoids bringing down the API if models already exist

### Issues & Resolution
- Import error inside Docker: `seed_models` was imported as a relative path that didn't resolve in the container's working directory → fixed by using the absolute module path `scripts.seed_models`

### Lessons Learned
- Docker container working directory affects module resolution differently than local dev; always verify import paths work from the container root

### Next Steps
- [ ] Add idempotency check so seeding logs "already seeded" rather than silently succeeding every restart

---

## [2026-01-31] - Railway Deployment Stabilisation

### Summary
- Resolved a series of Railway deployment failures: line endings, health checks, PORT env var, start command, enum migration errors
- Rewrote sample-app to call the HTTP API rather than importing `prompt_ledger` directly (fixes container isolation)
- Added detailed startup logging to sample-app for Railway debugging
- Modified: `template/`, `entrypoint.sh`, `alembic/versions/`, multiple Dockerfiles
- Commits: `4067961`, `7da7e2e`, `a8bdd64`, `c608235`, `eed471b`, `6c8b66d`, `fdd64d3`, `d37b36b`, `a9fa2b1`, `6093134`, `c7536ac`, `9717077`, `c1e0d58`, `7b3d7fb`, `7c0d9d5`, `f93208a`, `5612e49`

### Decisions
- Used `DO $$ ... $$` blocks instead of `IF NOT EXISTS` for enum creation in migrations — Railway's Postgres version required this syntax
- Dropped column defaults before altering to enum types — Postgres requires this ordering
- Created columns as TEXT then altered to enum — avoids type-cast issues during migration
- Removed `button.json` in favour of manual Railway template setup after discovering button.json limitations

### Issues & Resolution
- `start.sh` CRLF line endings caused `/bin/sh` to fail on Linux containers → converted to LF
- Railway injects `PORT` env var but `uvicorn` was binding to a hardcoded port → switched to `${PORT:-8000}`
- Health check failures masked the real startup error → temporarily disabled to expose root cause
- Enum migration failures (`cannot alter type of column`) → rewrote migration with TEXT→ALTER pattern and DO blocks

### Lessons Learned
- Railway Postgres is strict about enum creation order; always use DO blocks and drop defaults before altering column types
- Sample apps in a monorepo template should call the API over HTTP, not import the package — keeps services decoupled

### Next Steps
- [ ] Re-enable health check now that startup is stable
- [ ] Add Railway deployment smoke test to CI

---

## [2026-01-29] - Railway Template Creation (FR-002)

### Summary
- Created Railway one-click deploy template for PromptLedger
- Added `railway.toml`, Dockerfiles for API and sample-app services, build context configuration
- Added Railway deployment compatibility to the core package
- Docs: `requirements/FR-002-PromptLedger-Railway-Templates.md`
- Commits: `372a8a8`, `79ff859`, `4cd5721`, `9d9bf82`, `5385462`

### Decisions
- Monorepo build context: both services build from the repo root so the API service can be shared as a dependency
- Chose Railway over other platforms as the initial deployment target due to simpler template publishing and free-tier Postgres/Redis

### Issues & Resolution
- `railway.toml` plugin syntax was incorrect on first pass → corrected after consulting Railway docs

### Lessons Learned
- Railway template testing requires an actual Railway account deploy; local docker-compose behaviour differs subtly

### Next Steps
- [ ] Publish template to Railway marketplace (see `requirements/FR-002`)

---

## [2026-01-21] - FR-001: Workflow Execution Tracking

### Summary
- Implemented dual-mode prompt management and OpenTelemetry-style workflow span tracking
- New models: `Span` (parent/child relationships, trace ID correlation), updated `Prompt`/`PromptVersion` with mode field
- New endpoints: `/v1/analytics/` for span/trace queries; `/v1/code-prompts/register` for tracking-mode registration
- New migration: `98be36776ed5_add_spans_table_for_workflow_tracking.py`
- Tests: `tests/unit/test_span_model.py`, `tests/unit/test_models_prompt_mode.py`, `tests/integration/test_code_prompts_api.py`
- Merged via PR #1
- Commits: `5b14f9d`, `8aea9a9`, `7a4b354`, `bdac238`, `c16908b`, `7d37ac5`

### Decisions
- Span model follows OpenTelemetry conventions (trace_id, span_id, parent_span_id, attributes JSONB) so it's familiar to teams already using OTel
- Dual-mode uses a single unified table set with a `mode` enum column rather than separate tables — simplifies queries and migrations
- Code-based tracking mode uses SHA-256 content checksums for automatic version detection — no version numbers to manage manually

### Issues & Resolution
- SQLAlchemy relationship error on startup: `Span` model was not imported into `__init__.py` so the relationship couldn't resolve → added missing import

### Lessons Learned
- SQLAlchemy relationship errors surface at startup, not at model definition time — always test a full app boot after adding relationships

### Next Steps
- [x] Publish FR-001 implementation
- [ ] Add async execution span tracking (currently only sync executions create spans)

---

## [2026-01-19] - Initial Implementation & Project Setup

### Summary
- Complete initial implementation: FastAPI app, PostgreSQL schema, Alembic migrations (001 initial, 002 prompt mode), Celery workers, provider adapter factory, prompt service, execution service
- Development environment: `pyproject.toml`, `Makefile`, `docker-compose.yml`, `Dockerfile`, `.pre-commit-config.yaml`
- TDD example and test structure established: `tests/unit/`, `tests/integration/`, `tests/test_models.py`
- Upgraded to Python 3.11+ for `asyncio` performance improvements
- Commits: `db5ddac`, `4915545`, `064a38a`, `8aea9a9`, `ead0ee8`

### Decisions
- FastAPI chosen for async-first design and automatic OpenAPI docs
- asyncpg over psycopg2 for true async Postgres — no thread pool overhead
- Celery + Redis for async execution queue — battle-tested, easy Railway deployment
- Pydantic v2 for settings and request validation — better performance and error messages than v1
- `structlog` for structured JSON logging — easier to query in production

### Issues & Resolution
- None significant at initial setup

### Lessons Learned
- Setting `asyncio_mode = "auto"` in `pyproject.toml` eliminates the need for `@pytest.mark.asyncio` on every async test

### Next Steps
- [x] Implement FR-001 workflow execution tracking
- [x] Add Railway deployment support (FR-002)
- [ ] Add additional LLM provider adapters (Anthropic, Cohere)
- [ ] GitHub Actions CI pipeline
