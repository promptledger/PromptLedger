# PromptLedger - Implementation TODO List

**Last Updated:** 2026-01-19
**Status:** Post-Initial Implementation - Verification & Completion Phase

---

## Environment Assessment

### Current Environment
- **OS:** Windows (win32)
- **Python:** 3.9.13 ⚠️ *Spec requires 3.11+*
- **Node.js:** v22.12.0
- **Docker:** 29.0.1
- **Docker Compose:** v2.40.3-desktop.1
- **Git:** Repository initialized, on master branch
- **Virtual Environment:** Exists (.venv)
- **Pre-commit Hooks:** Configured (.pre-commit-config.yaml)
- **.env File:** ❌ Not found (needs creation from .env.example)

### Dependencies Installed
- FastAPI, Uvicorn, SQLAlchemy, Alembic
- Redis, Celery
- OpenAI SDK, Jinja2, Pydantic
- Testing: pytest (assumed from dev setup)

---

## 1. Configuration & Environment Setup

### 1.1 Critical Configuration Tasks
- [ ] **CRITICAL: Upgrade Python to 3.11+**
  - Current: 3.9.13
  - Required: 3.11+ per spec (Section 2)
  - Impact: Type hints, performance improvements
  - Action: Install Python 3.11 or 3.12, recreate venv

- [ ] **Create .env file from .env.example**
  - Copy .env.example to .env
  - Add actual OPENAI_API_KEY
  - Review and update API_KEY for security
  - Verify DATABASE_URL and REDIS_URL

- [ ] **Verify all required environment variables**
  - DATABASE_URL
  - REDIS_URL
  - OPENAI_API_KEY (required, no default)
  - API_KEY (security critical)
  - DEBUG mode setting

### 1.2 Development Environment Setup
- [ ] **Install/Reinstall dependencies after Python upgrade**
  ```bash
  pip install -e ".[dev]"
  ```

- [ ] **Verify pre-commit hooks are working**
  ```bash
  pre-commit run --all-files
  ```

- [ ] **Test Docker services can start**
  ```bash
  docker-compose up -d postgres redis
  ```

---

## 2. Database Verification & Setup

### 2.1 Schema Verification
- [ ] **Verify Alembic migration 001_initial_schema.py matches spec**
  - Review against Section 7 (Postgres Schema)
  - Verify all 4 ENUM types created:
    - `prompt_version_status` (draft, active, deprecated)
    - `execution_mode` (sync, async)
    - `execution_status` (queued, running, succeeded, failed, canceled)
    - `provider_name` (openai)
  - Verify all 5 tables created with correct columns
  - Verify all indexes and constraints

- [ ] **Run database migrations**
  ```bash
  alembic upgrade head
  ```

- [ ] **Verify database schema in Postgres**
  - Check tables exist
  - Check indexes exist (Section 7.5 - 4 indexes on executions)
  - Check constraints (foreign keys, unique constraints)

### 2.2 Database Seeding
- [ ] **Verify seed_models script exists**
  - Check if `src/prompt_ledger/scripts/seed_models.py` exists
  - If not, create it

- [ ] **Seed initial OpenAI models**
  - gpt-4o-mini
  - gpt-4o
  - gpt-4-turbo
  - Set max_tokens and supports_streaming flags
  - Run: `python -m prompt_ledger.scripts.seed_models`

---

## 3. API Implementation Verification

### 3.1 Core Endpoints (Section 9)

#### Prompt Management
- [ ] **PUT /v1/prompts/{name} - Prompt Upsert**
  - Verify versioning logic (Section 6):
    - Checksum-based deduplication
    - Version number increment only on content change
    - Active version pointer update
  - Verify request/response schemas match spec
  - Test with existing prompts (update case)
  - Test with new prompts (create case)

- [ ] **GET /v1/prompts/{name} - Get Prompt**
  - Return prompt with active version
  - Include metadata

- [ ] **GET /v1/prompts/{name}/versions - List Versions**
  - Return all versions for a prompt
  - Include version metadata

#### Execution Endpoints
- [ ] **POST /v1/executions:run - Sync Execution**
  - Verify inline execution flow
  - Verify response includes telemetry
  - Test with various models
  - Test error handling

- [ ] **POST /v1/executions:submit - Async Execution**
  - Verify queue submission to Redis/Celery
  - Verify execution record created with status=queued
  - Verify response format
  - Test idempotency key support

- [ ] **GET /v1/executions/{execution_id} - Poll Execution**
  - Verify returns current status
  - Verify response format matches spec
  - Test with various execution statuses

### 3.2 Authentication & Middleware
- [ ] **Verify X-API-Key authentication**
  - Test all endpoints require valid API key
  - Test rejection of invalid/missing keys
  - Verify header name is exactly "X-API-Key"

- [ ] **Verify Idempotency-Key support**
  - Test on submit endpoint
  - Test on run endpoint
  - Verify duplicate prevention (Section 7.5 - unique constraint)

### 3.3 Health Check
- [ ] **Verify GET /health endpoint**
  - Returns 200 OK
  - Returns {"status": "healthy"}

---

## 4. Rendering Engine (Section 5)

- [ ] **Verify Jinja2 rendering implementation**
  - Variables are rendered before enqueue
  - Undefined variables cause errors (fail fast)
  - Both rendered_prompt and variables_json are stored

- [ ] **Test rendering edge cases**
  - Missing variables (should error)
  - Complex nested variables
  - Special characters in variables

---

## 5. Worker Implementation (Section 10)

### 5.1 Celery Worker
- [ ] **Verify worker task implementation**
  - Load execution row by ID
  - Update status to "running" + set started_at
  - Call provider adapter
  - Update with results (success case)
  - Update with errors (failure case)
  - Set completed_at

- [ ] **Verify retry logic**
  - Max 3 retries
  - Exponential backoff (5s, 30s, 2m)
  - Retry conditions: timeouts, 429, 5xx
  - No retry on other 4xx

- [ ] **Test worker can be started**
  ```bash
  celery -A prompt_ledger.workers.celery_app worker --loglevel=info
  ```

### 5.2 Queue Integration
- [ ] **Verify Redis connection**
  - Worker connects to Redis
  - Tasks are enqueued correctly
  - Tasks are consumed correctly

---

## 6. Provider Adapter (Section 11)

### 6.1 OpenAI Adapter
- [ ] **Verify OpenAI adapter implementation**
  - Implements ProviderAdapter interface
  - generate() method signature correct
  - Returns dict with required fields:
    - response_text
    - prompt_tokens
    - response_tokens
    - latency_ms
    - provider_request_id

- [ ] **Verify parameter mapping**
  - temperature
  - top_k (if supported)
  - top_p
  - max_new_tokens → max_tokens
  - repetition_penalty

- [ ] **Verify error handling**
  - Timeouts
  - Rate limiting (429)
  - Server errors (5xx)
  - Invalid API key

- [ ] **Test with actual OpenAI API**
  - Requires valid OPENAI_API_KEY
  - Test with gpt-4o-mini
  - Verify token counting works
  - Verify latency tracking works

---

## 7. Truncation & Limits (Section 12)

- [ ] **Verify truncation implementation**
  - Max rendered_prompt: 200 KB
  - Max response_text: 500 KB
  - Truncated responses set error_type = "truncated"

- [ ] **Test truncation**
  - Create test with >200KB prompt
  - Create test with >500KB response (mock)

---

## 8. Testing

### 8.1 Existing Tests
- [ ] **Review test_models.py**
  - Verify covers all model operations
  - Add missing test cases

- [ ] **Review test_prompts.py**
  - Verify covers all prompt operations
  - Add missing test cases

### 8.2 Missing Test Files
- [ ] **Create test_executions.py**
  - Test sync execution flow
  - Test async execution flow
  - Test polling
  - Test idempotency

- [ ] **Create test_versioning.py**
  - Test checksum deduplication
  - Test version number increment
  - Test active version pointer

- [ ] **Create test_rendering.py**
  - Test Jinja2 rendering
  - Test variable substitution
  - Test error on undefined variables

- [ ] **Create test_workers.py**
  - Test worker task execution
  - Test retry logic
  - Test error handling

- [ ] **Create test_providers.py**
  - Test OpenAI adapter
  - Test parameter mapping
  - Mock OpenAI API responses

### 8.3 Integration Tests
- [ ] **Create test_end_to_end.py**
  - Test full sync execution flow
  - Test full async execution flow
  - Test prompt versioning through execution

### 8.4 Run All Tests
- [ ] **Execute test suite**
  ```bash
  pytest -v
  pytest --cov=src/prompt_ledger
  ```

---

## 9. Observability (Section 13)

- [ ] **Verify logging implementation**
  - Uses structlog (already in requirements)
  - Logs per execution include:
    - execution_id
    - provider
    - model_name
    - latency
    - token counts
    - status

- [ ] **Test logging output**
  - Verify logs are structured
  - Verify all required fields present

---

## 10. End-to-End Verification (Section 15 - Definition of Done)

### 10.1 MVP Completion Checklist
- [ ] **Prompts can be registered and versioned via API**
  - Create a new prompt
  - Update prompt (new version)
  - Update prompt with same content (no new version)

- [ ] **Active version resolution works**
  - Execute without specifying version (uses active)
  - Execute with specific version number

- [ ] **Async submit + worker execution works**
  - Submit async execution
  - Worker picks up task
  - Worker completes task

- [ ] **Polling returns results**
  - Poll queued execution
  - Poll running execution
  - Poll completed execution

- [ ] **Executions are fully traceable in Postgres**
  - Query executions table
  - Join with prompts, versions, models
  - Verify lineage

- [ ] **Idempotency prevents duplicate executions**
  - Submit with idempotency key
  - Re-submit with same key
  - Verify only one execution

- [ ] **OpenAI adapter works end-to-end**
  - Real API call to OpenAI
  - Response captured
  - Tokens counted
  - Latency recorded

### 10.2 Full Stack Test
- [ ] **Run complete stack with Docker Compose**
  ```bash
  docker-compose up -d
  docker-compose logs -f
  ```

- [ ] **Execute complete workflow**
  1. Create/register a prompt
  2. Execute sync
  3. Execute async
  4. Poll until completion
  5. Verify results in database

---

## 11. Documentation & Code Quality

### 11.1 Code Quality
- [ ] **Run formatters**
  ```bash
  black src/ tests/
  isort src/ tests/
  ```

- [ ] **Run type checker**
  ```bash
  mypy src/
  ```

- [ ] **Fix any linting issues**

### 11.2 Documentation
- [ ] **Review README.md**
  - Update with any missing instructions
  - Verify all examples work
  - Add troubleshooting section if needed

- [ ] **Add API documentation**
  - FastAPI auto-generates docs at /docs
  - Verify Swagger UI works
  - Add example requests/responses

- [ ] **Add docstrings**
  - Verify all public functions have docstrings
  - Verify all classes have docstrings

---

## 12. Production Readiness (Future)

### 12.1 Security
- [ ] **API key management**
  - Document key rotation process
  - Consider adding key expiration

- [ ] **Secrets management**
  - Document best practices for OPENAI_API_KEY
  - Consider integration with secret managers

### 12.2 Deployment
- [ ] **Create docker-compose.prod.yml**
  - Remove dev-specific settings
  - Add production logging
  - Add health checks

- [ ] **Document deployment process**
  - Update README with production guidance
  - Add monitoring recommendations

### 12.3 Performance
- [ ] **Load testing**
  - Test with high concurrency
  - Test worker scaling
  - Identify bottlenecks

- [ ] **Database optimization**
  - Verify indexes are effective
  - Consider partitioning for executions table (future)

---

## Priority Levels

### P0 - Critical (Blocks MVP)
1. Python version upgrade to 3.11+
2. Create .env file with valid credentials
3. Database migration verification
4. All MVP Definition of Done items (Section 10.1)

### P1 - High (Required for MVP)
1. Complete test coverage for core flows
2. Provider adapter verification with real API
3. Worker retry logic verification
4. API authentication verification

### P2 - Medium (Important but not blocking)
1. Integration tests
2. Code quality checks (mypy, black, isort)
3. Documentation updates
4. Logging verification

### P3 - Low (Nice to have)
1. Production deployment setup
2. Load testing
3. Additional documentation

---

## Notes

- **Current Status:** The basic implementation appears complete based on file structure
- **Next Steps:** Start with P0 items, particularly Python upgrade and environment setup
- **Testing Strategy:** Verify each component works before moving to integration tests
- **Risk Areas:**
  - OpenAI API integration (requires valid key and credits)
  - Worker retry logic (needs thorough testing)
  - Versioning deduplication (critical for correctness)
- **Dependencies:** Cannot fully test without:
  - Python 3.11+
  - Valid .env file with OPENAI_API_KEY
  - Running Docker services
