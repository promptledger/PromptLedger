# PromptLedger - Implementation TODO List

**Last Updated:** 2026-01-19
**Status:** Post-Initial Implementation - Verification & Completion Phase
**Major Update:** Dual-Mode Prompt Management (Full + Code-Based Tracking) added to spec

---

## Environment Assessment

### Current Environment
- **OS:** Windows (win32)
- **Python (System):** 3.9.13 (Anaconda)
- **Python (Virtual Env):** 3.11.2 ✅ *Meets spec requirement 3.11+*
- **Node.js:** v22.12.0
- **Docker:** 29.0.1
- **Docker Compose:** v2.40.3-desktop.1
- **Git:** Repository initialized, on master branch
- **Virtual Environment:** Exists (.venv) with Python 3.11.2
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
- [x] **CRITICAL: Upgrade Python to 3.11+**
  - ✅ Virtual environment has Python 3.11.2
  - Meets spec requirement (Section 2)

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
- [ ] **Verify dependencies are installed in virtual environment**
  ```bash
  .venv/Scripts/pip list
  # Or reinstall if needed:
  .venv/Scripts/pip install -e ".[dev]"
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
  - **NEW: Check if `prompts.mode` field exists for dual-mode support**
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

## 4. Code-Based Prompt Mode Implementation (NEW - Section 10 in Spec)

### 4.1 Database Schema Updates
- [ ] **Add `mode` field to prompts table**
  - Create migration to add `mode` column (ENUM: 'full', 'tracking')
  - Default value: 'full' for backward compatibility
  - Update existing prompts to 'full' mode
  - Add index on mode field for analytics queries

- [ ] **Verify schema supports dual-mode**
  - Confirm prompt_versions table works for both modes
  - Confirm executions table works for both modes
  - No separate tables needed (unified design)

### 4.2 Core Code-Based APIs (Section 10)

#### Register Code Prompts
- [ ] **POST /v1/prompts/register-code**
  - Accept array of prompts with name, template_source, template_hash
  - For each prompt:
    - Check if prompt exists by name
    - Compute checksum from template_source
    - If checksum differs: create new version, increment version_number
    - If checksum same: return existing version
    - Set mode='tracking'
  - Return registration results with version info and change detection
  - Write tests for:
    - First-time registration
    - Re-registration with no changes (no new version)
    - Re-registration with changes (new version created)
    - Bulk registration (multiple prompts)

#### Execute Code Prompt
- [ ] **POST /v1/prompts/{name}/execute**
  - Accept variables, version (optional), model_name, mode
  - Verify prompt exists and mode='tracking'
  - Resolve version (use specified or latest)
  - Execute prompt (sync or async based on mode parameter)
  - Track execution in same executions table
  - Write tests for:
    - Sync execution
    - Async execution
    - Version pinning
    - Error handling (prompt not found, wrong mode)

#### Get Prompt History (Unified)
- [ ] **GET /v1/prompts/{name}/history?mode={mode}**
  - Return version history with execution counts
  - Support both 'full' and 'tracking' modes
  - Include version metadata (template_hash, created_at)
  - Write tests for:
    - Full mode history
    - Tracking mode history
    - Prompt not found

#### Unified Analytics
- [ ] **GET /v1/analytics/prompts?mode={all|full|tracking}**
  - Aggregate execution stats by mode
  - Return:
    - Total executions
    - Prompts by mode count
    - Average latency by mode
    - Token usage by mode
  - Write tests for:
    - All modes analytics
    - Mode-specific filtering
    - Empty data handling

### 4.3 Client SDK Support (Code Examples)

- [ ] **Create Python SDK examples**
  - Full management mode example
  - Code-based tracking mode example
  - Migration between modes example
  - Add to README.md

- [ ] **Document prompt class pattern**
  ```python
  class Prompts:
      WELCOME = "Hello {{name}}!"

      @classmethod
      def get_template(cls, name):
          return getattr(cls, name)
  ```

### 4.4 Change Detection & Versioning

- [ ] **Implement automatic version detection**
  - Compare template_hash on registration
  - Auto-increment version on content change
  - Preserve version on re-registration with same content
  - Log version changes for audit

- [ ] **Test version detection edge cases**
  - Whitespace-only changes (should create new version)
  - Case changes in template (should create new version)
  - Variable name changes (should create new version)
  - Same content re-registration (should NOT create new version)

### 4.5 Mode Management

- [ ] **Implement mode validation**
  - Cannot execute 'full' mode prompts via code-based endpoints
  - Cannot execute 'tracking' mode prompts via traditional PUT
  - Clear error messages for mode mismatches

- [ ] **Add mode migration support (future)**
  - Document migration path from tracking → full
  - Document migration path from full → tracking
  - Add helper endpoints if needed

### 4.6 Integration Testing

- [ ] **End-to-end code-based workflow test**
  1. Register multiple code prompts
  2. Execute each prompt (sync and async)
  3. Verify version creation on content change
  4. Verify no version creation on re-registration
  5. Query analytics for tracking mode
  6. Query prompt history for tracking mode

- [ ] **Mixed mode testing**
  - Create prompts in both full and tracking modes
  - Execute prompts from both modes
  - Verify unified analytics work correctly
  - Verify mode isolation (no cross-contamination)

---

## 5. Rendering Engine (Section 5)

- [ ] **Verify Jinja2 rendering implementation**
  - Variables are rendered before enqueue
  - Undefined variables cause errors (fail fast)
  - Both rendered_prompt and variables_json are stored

- [ ] **Test rendering edge cases**
  - Missing variables (should error)
  - Complex nested variables
  - Special characters in variables

---

## 6. Worker Implementation (Section 11)

### 6.1 Celery Worker
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

### 6.2 Queue Integration
- [ ] **Verify Redis connection**
  - Worker connects to Redis
  - Tasks are enqueued correctly
  - Tasks are consumed correctly

---

## 7. Provider Adapter (Section 11)

### 7.1 OpenAI Adapter
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

## 8. Truncation & Limits (Section 12)

- [ ] **Verify truncation implementation**
  - Max rendered_prompt: 200 KB
  - Max response_text: 500 KB
  - Truncated responses set error_type = "truncated"

- [ ] **Test truncation**
  - Create test with >200KB prompt
  - Create test with >500KB response (mock)

---

## 9. Testing

### 9.1 Existing Tests
- [ ] **Review test_models.py**
  - Verify covers all model operations
  - Add missing test cases

- [ ] **Review test_prompts.py**
  - Verify covers all prompt operations
  - Add missing test cases

### 9.2 Missing Test Files
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

- [ ] **Create test_code_based_prompts.py (NEW)**
  - Test prompt registration with tracking mode
  - Test version detection on content change
  - Test no version creation on re-registration
  - Test code-based execution endpoint
  - Test mode validation (tracking vs full)
  - Test unified analytics with both modes
  - Test prompt history for tracking mode

### 9.3 Integration Tests
- [ ] **Create test_end_to_end.py**
  - Test full sync execution flow
  - Test full async execution flow
  - Test prompt versioning through execution
  - **NEW: Test code-based prompt workflow**
  - **NEW: Test mixed mode operations (full + tracking)**

### 9.4 Run All Tests
- [ ] **Execute test suite**
  ```bash
  pytest -v
  pytest --cov=src/prompt_ledger
  ```

---

## 10. Observability (Section 13)

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

## 11. End-to-End Verification (Section 15 - Definition of Done)

### 11.1 MVP Completion Checklist - Full Management Mode
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

### 11.2 MVP Completion Checklist - Code-Based Tracking Mode (NEW)

- [ ] **Code prompts can be registered with automatic versioning**
  - Register multiple prompts via POST /v1/prompts/register-code
  - Verify version detection on first registration
  - Update prompt content and re-register
  - Verify new version created automatically

- [ ] **Content change detection works correctly**
  - Re-register unchanged prompt (no new version)
  - Change template content (new version created)
  - Verify checksum-based deduplication

- [ ] **Code-based execution works**
  - Execute tracking mode prompt (sync)
  - Execute tracking mode prompt (async)
  - Verify execution tracked in same executions table

- [ ] **Mode isolation enforced**
  - Cannot execute full mode prompt via code-based endpoint
  - Cannot execute tracking mode prompt via traditional PUT
  - Clear error messages for mode mismatches

- [ ] **Unified analytics work across both modes**
  - Query analytics with mode=all
  - Verify both full and tracking mode stats
  - Query mode-specific analytics

- [ ] **Prompt history works for both modes**
  - Get history for full mode prompt
  - Get history for tracking mode prompt
  - Verify version metadata and execution counts

### 11.3 Full Stack Test
- [ ] **Run complete stack with Docker Compose**
  ```bash
  docker-compose up -d
  docker-compose logs -f
  ```

- [ ] **Execute complete workflow (Full Mode)**
  1. Create/register a prompt via PUT
  2. Execute sync
  3. Execute async
  4. Poll until completion
  5. Verify results in database

- [ ] **Execute complete workflow (Tracking Mode - NEW)**
  1. Register code-based prompts
  2. Execute via code-based endpoint (sync)
  3. Execute via code-based endpoint (async)
  4. Query unified analytics
  5. Verify version auto-detection

---

## 12. Documentation & Code Quality

### 12.1 Code Quality
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

### 12.2 Documentation
- [ ] **Review README.md**
  - ✅ Already updated with dual-mode documentation
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

## 13. Production Readiness (Future)

### 13.1 Security
- [ ] **API key management**
  - Document key rotation process
  - Consider adding key expiration

- [ ] **Secrets management**
  - Document best practices for OPENAI_API_KEY
  - Consider integration with secret managers

### 13.2 Deployment
- [ ] **Create docker-compose.prod.yml**
  - Remove dev-specific settings
  - Add production logging
  - Add health checks

- [ ] **Document deployment process**
  - Update README with production guidance
  - Add monitoring recommendations

### 13.3 Performance
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
1. ~~Python version upgrade to 3.11+~~ ✅ Complete
2. Create .env file with valid credentials
3. Database migration verification (including new `mode` field)
4. All MVP Definition of Done items (Sections 11.1 & 11.2)
5. **NEW: Code-based prompt mode implementation (Section 4)**

### P1 - High (Required for MVP)
1. Complete test coverage for core flows (both modes)
2. Provider adapter verification with real API
3. Worker retry logic verification
4. API authentication verification
5. **NEW: Code-based APIs implementation (register, execute, history, analytics)**
6. **NEW: Mode validation and isolation**

### P2 - Medium (Important but not blocking)
1. Integration tests (including mixed-mode scenarios)
2. Code quality checks (mypy, black, isort)
3. Documentation updates (README already done)
4. Logging verification
5. **NEW: Client SDK examples for both modes**

### P3 - Low (Nice to have)
1. Production deployment setup
2. Load testing
3. Additional documentation

---

## Notes

- **Current Status:** Basic implementation appears complete, **NEW dual-mode architecture added**
- **Major Update:** Code-based prompt tracking mode added to support developer-centric workflows
- **Next Steps:**
  - ~~Python 3.11+ upgrade~~ ✅ Complete
  - Create .env file with credentials
  - Implement code-based prompt mode (Section 4)
  - Verify existing implementation works
- **Testing Strategy:**
  - Verify legacy full-mode components first
  - Implement and test code-based mode separately
  - Test unified analytics and mixed-mode scenarios
  - Verify mode isolation and validation
- **Risk Areas:**
  - OpenAI API integration (requires valid key and credits)
  - Worker retry logic (needs thorough testing)
  - Versioning deduplication (critical for correctness)
  - **NEW: Mode validation and isolation** (prevent cross-mode contamination)
  - **NEW: Automatic version detection** (checksum comparison)
- **Dependencies:** Cannot fully test without:
  - ~~Python 3.11+~~ ✅ Complete (venv has 3.11.2)
  - Valid .env file with OPENAI_API_KEY
  - Running Docker services
- **Architecture Changes:**
  - Unified table design supports both modes (no duplication)
  - `prompts.mode` field distinguishes between 'full' and 'tracking'
  - Same execution tracking for both modes
  - 4 new API endpoints for code-based operations
