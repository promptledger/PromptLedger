# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**PromptLedger** is an open-source prompt registry, execution, and lineage service for GenAI/agentic applications. It solves "prompt sprawl" by providing a centralized control plane for managing prompt versions, tracking executions, and auditing LLM call lineage.

**Core capabilities:**
- Dual-mode prompt management: database-driven (full) vs code-based (tracking)
- Content-based versioning via SHA-256 checksums (automatic deduplication)
- Sync and async execution via Celery/Redis
- OpenTelemetry-style workflow span tracking
- Multi-provider LLM support via adapter factory pattern

## Architecture

**Stack:** FastAPI + PostgreSQL (asyncpg) + Redis + Celery, deployed via Docker / Railway

**Layers:**
1. **API** (`src/prompt_ledger/api/`) — FastAPI app, versioned under `/v1/`, API key auth via `X-API-Key` header
2. **Services** (`src/prompt_ledger/services/`) — Business logic: `PromptService`, `ExecutionService`, `ProviderAdapterFactory`
3. **Models** (`src/prompt_ledger/models/`) — SQLAlchemy async ORM: `Prompt`, `PromptVersion`, `Execution`, `ExecutionInput`, `Span`, `Model`
4. **Workers** (`src/prompt_ledger/workers/`) — Celery app + async execution tasks
5. **DB** (`src/prompt_ledger/db/`) — Async SQLAlchemy session management, `init_db()`

**Dual-Mode System:**
- `full` mode: prompts managed via API (create/update/render/execute through endpoints)
- `tracking` mode: prompts defined in code, registered via `/v1/code-prompts/register`, auto-versioned on template changes

**Span Tracking (FR-001):** OpenTelemetry-style parent/child spans, trace ID correlation, supports nested agent trees and ReAct loops.

## Commands

**Setup:**
```bash
pip install -e ".[dev]"   # install with dev deps
pre-commit install         # install git hooks
cp .env.example .env       # configure env vars
```

**Development (Docker):**
```bash
make docker-up    # start postgres + redis + api + worker
make migrate      # alembic upgrade head
make seed         # seed default AI models
make docker-down
```

**Development (local):**
```bash
docker-compose up -d postgres redis          # infra only
alembic upgrade head
uvicorn prompt_ledger.api.main:app --reload  # Terminal 1
celery -A prompt_ledger.workers.celery_app worker --loglevel=info  # Terminal 2
```

**Makefile shortcuts:**
```bash
make test     # pytest with coverage
make lint     # flake8 + mypy
make format   # black + isort
make run      # uvicorn dev server
make worker   # celery worker
make migration MSG="describe change"  # create new migration
```

## Testing

**Run tests:**
```bash
pytest                                               # all tests
pytest -v --cov=src/prompt_ledger --cov-report=html  # with HTML coverage
pytest tests/unit/                                   # unit only
pytest tests/integration/                            # integration only
pytest tests/test_prompts.py::test_name              # single test
```

**Structure:** `tests/unit/` (service & model logic), `tests/integration/` (API endpoints), `tests/test_models.py` (ORM constraints)

**Coverage target: 90%+**

**`asyncio_mode = "auto"`** is set in `pyproject.toml` — all async tests work without explicit `@pytest.mark.asyncio`.

**TDD — HARD RULE, NO EXCEPTIONS:**
1. Write the failing test first
2. Run it — confirm RED (import error or assertion failure counts)
3. Write minimum implementation to pass
4. Run again — confirm GREEN
5. Refactor, then commit

**NEVER write implementation code before a failing test exists. Stop and write tests first.**

## Progress Tracking

**CRITICAL:** After every commit, update `progress_tracker.md` (root directory, newest entries first). Also review `README.md` and update it to reflect the current state.

**Entry template:**
```markdown
## [YYYY-MM-DD] - [Title]

### Summary
- Files changed, tests written, coverage %

### Decisions
- Technical choices + rationale, alternatives rejected

### Issues & Resolution
- Problems encountered, error messages, how fixed

### Lessons Learned
- Key insights, what worked/didn't work

### Next Steps
- [ ] Actionable tasks
```

## Requirements Tracking

Feature requests and functional requirements live in `requirements/`. Each requirement gets its own file named `FR-NNN-short-description.md`.

**Existing requirements:**
- `requirements/FR-001-workflow-execution-tracking.md` — Workflow span tracking (implemented)
- `requirements/FR-002-PromptLedger-Railway-Templates.md` — Railway template deployment
- `requirements/FR-003-unified-execution-client.md` — Unified execution client: `messages` input, auto-span, `execute()` SDK method (proposed)
- `requirements/RailwayTemplates.md` — Railway templates reference
- `requirements/promptledger_epic_1_integration_enhancements.md` — Epic 1: Anthropic provider, Python SDK, dry-run registration, cost model, span ingestion API, docs (active)
- `requirements/promptledger_epic_2_namespacing.md` — Epic 2: Project namespacing and multi-tenant API keys (deferred)
- `requirements/srf_epic_decomposition.md` — Synthetic Research Forum technical spec and epic breakdown

**When implementing a requirement:** reference its FR number in commit messages and progress tracker entries. Update the requirement file's `Status` field as it progresses (`Proposed` → `In Progress` → `Implemented`).

**When adding a new requirement:** create `requirements/FR-NNN-title.md` and reference it in CLAUDE.md above.

**Story format standard:** Every story in every requirement file must include an agile user story block immediately after the story heading, before the Goal line:

```markdown
## Writing Epics, Stories, Bugs & Tech Debt

**Full standards and templates:** `requirements/EPIC_TEMPLATE.md` — read this before writing any requirements artefact.

**Key rules (full detail in template):**
- Stories use the Agile format: **"As a [role], I would like [capability], so that [benefit]."**
- Acceptance criteria are written in **Gherkin** (`Scenario` / `Given` / `When` / `Then`). Each scenario maps 1:1 to a pytest test function.
- Every story must include at least one **negative/unhappy-path** Gherkin scenario.
- Bug documents go in `requirements/bugs/BUG-{NN}-{slug}.md`. Each root cause must name the file + line + a code snippet.
- Tech debt entries go at the **bottom** of `requirements/tech_debt_tracker.md` with a specific trigger condition — not "someday".
- Epic numbers are sequential; check existing files for the next N before creating.

## Configuration

**Required `.env` variables:**
```ini
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/prompt_ledger
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=your-key
API_KEY=dev-key-change-in-production   # MUST change in production
```

Settings are managed via Pydantic `BaseSettings` in `src/prompt_ledger/settings.py`. Never hardcode config values in source files — always read from `settings`.

**Postgres URL:** The settings class auto-converts `postgres://` → `postgresql+asyncpg://` for Railway compatibility.

## Database & Migrations

**ORM:** SQLAlchemy 2.0 async (`AsyncSession`). All DB calls use `await`.

**Migrations via Alembic:**
```bash
alembic upgrade head                            # apply all migrations
alembic revision --autogenerate -m "message"    # generate new migration
```

Migration files live in `alembic/versions/`. Always review autogenerated migrations before applying — Alembic doesn't detect all changes correctly.

**Model seeding:** `scripts/seed_models.py` seeds default AI provider models. Runs automatically at API startup via the lifespan handler, and manually via `make seed`.

## Critical Patterns

**API authentication:** All endpoints (except `/health`) require `X-API-Key` header matching `settings.api_key`.

**Async everywhere:** All service methods, DB calls, and endpoint handlers are `async`. Do not introduce sync I/O in the async path.

**Content-based versioning:** `PromptVersion` uses `compute_checksum()` (SHA-256 of template). Registering the same template twice returns the existing version — no duplicate is created.

**Provider adapters:** New LLM providers go in `services/providers.py` following the adapter pattern. Register in `ProviderAdapterFactory`. Never call provider SDKs directly from endpoints.

**Structured logging:** Use `structlog` with key=value context. Follow the existing pattern in the codebase.

**Migrations for schema changes:** Every model change requires an Alembic migration. Do not use `init_db()` / `create_all()` to manage schema in production — that is for test environments only.

## Pitfalls

1. **Railway DATABASE_URL:** Railway injects `postgres://` (no `+asyncpg`). The settings class handles conversion; bypassing it causes connection errors.
2. **Async session scope:** Never share an `AsyncSession` across requests or tasks. Always get a fresh session via the `get_db` dependency.
3. **Celery serialization:** Task arguments must be JSON-serializable. Pass IDs, not SQLAlchemy model instances — reload inside the task.
4. **Mode enforcement:** `full` and `tracking` mode prompts use separate endpoints. Don't skip mode validation.
5. **Pre-commit hooks:** `black`, `isort`, `mypy`, and `flake8` run on commit. Fix all issues rather than using `--no-verify`.
6. **`init_db()` is for tests only:** Production schema is managed exclusively via Alembic migrations.
7. **Span parent relationships:** Always set `parent_span_id` on child spans — orphaned spans break trace reconstruction.

## Key Files

| File | Purpose |
|------|---------|
| `src/prompt_ledger/settings.py` | All configuration via Pydantic Settings |
| `src/prompt_ledger/api/main.py` | FastAPI app, lifespan, middleware |
| `src/prompt_ledger/api/v1/endpoints/` | Route handlers (prompts, executions, code_prompts, analytics) |
| `src/prompt_ledger/services/prompt_service.py` | Dual-mode prompt logic |
| `src/prompt_ledger/services/execution.py` | Execution orchestration |
| `src/prompt_ledger/services/providers.py` | LLM provider adapters |
| `src/prompt_ledger/models/` | ORM models |
| `alembic/versions/` | Database migration history |
| `scripts/seed_models.py` | Default model seeding |
| `requirements/` | Feature requirements (FR-NNN files) |
| `progress_tracker.md` | Running dev log (newest first) |
| `docker-compose.yml` | Dev infrastructure |
| `Makefile` | Common dev commands |

## Resources

- `ARCHITECTURE.md` — detailed system design and component descriptions
- `CONTRIBUTING.md` — contribution workflow and code style guide
- `TEST_README.md` — testing framework details and coverage guidelines
- `INTEGRATION_GUIDE.md` — integrating PromptLedger into external apps
- FastAPI docs: https://fastapi.tiangolo.com/
- SQLAlchemy async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alembic docs: https://alembic.sqlalchemy.org/
