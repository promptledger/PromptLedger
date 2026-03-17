# Progress Tracker

Newest entries first. Updated after every commit.

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
