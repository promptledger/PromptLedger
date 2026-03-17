# Progress Tracker

Newest entries first. Updated after every commit.

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
