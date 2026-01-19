# Claude Development Guide - PromptLedger

**Project:** Prompt Registry, Execution & Lineage Service
**Version:** MVP (0.1.0)
**Python:** 3.11+ (Virtual env: 3.11.2)
**Status:** Post-initial implementation - Verification & Completion Phase

---

## 🎯 Project Mission

Build an **enterprise-grade Prompt Registry, Execution and Lineage Control Plane** that provides:
- **Dual-mode prompt management**: Full database management OR code-based tracking
- Centralized, governed control plane for GenAI prompts
- Content-based versioning with deduplication
- **Automatic versioning for code-based prompts** with change detection
- Multi-provider execution (OpenAI first, extensible)
- Async-first production execution with Redis + Celery
- Full execution lineage and telemetry in Postgres
- Deterministic reproducibility (prompt → version → execution)
- **Unified API and analytics** across both management modes

---

## 🚨 ABSOLUTE MANDATORY RULES

### 1. TEST-DRIVEN DEVELOPMENT (TDD) - NON-NEGOTIABLE ⚡

**NEVER write production code without first writing a failing test.**

#### Red-Green-Refactor Cycle - ALWAYS
1. **RED**: Write a failing test first
2. **GREEN**: Write minimal code to make it pass
3. **REFACTOR**: Clean up while keeping tests green

#### TDD for Every Change Type
- **New Feature**: Write acceptance test → integration tests → unit tests → implement
- **Bug Fix**: Write test reproducing bug → fix → add regression tests
- **Enhancement**: Write tests for new behavior → ensure existing pass → refactor

#### No Exceptions
- Even for "simple" changes
- Even for "quick fixes"
- Even for "emergency" patches
- **Code review will reject PRs without proper tests**

### 2. Test Coverage Requirements
- **Minimum 90% coverage** (no decrease from baseline)
- **100% coverage** of business logic
- Test both happy path AND error conditions
- Use descriptive test names explaining the scenario

### 3. Code Quality Gates
- All code must pass: `black`, `isort`, `flake8`, `mypy`
- All tests must pass before commit
- Pre-commit hooks enforce standards
- CI/CD pipeline blocks non-compliant code

---

## 📐 Architectural Decisions (Locked - From Spec)

### Core Technology Stack
| Component | Technology | Why |
|-----------|-----------|-----|
| API Framework | FastAPI | Async-first, auto-docs, type safety |
| Database | PostgreSQL 15+ | ACID, JSONB, async support |
| Queue System | Redis + Celery | Proven, reliable, scalable |
| Versioning | SHA256 checksum | Content-based deduplication |
| **Prompt Management** | **Dual-mode** | **Full DB OR code-based tracking** |
| Authentication | X-API-Key header | Simple internal auth |
| Rendering | Jinja2 | Industry standard templating |
| Provider (MVP) | OpenAI only | Focus, extensible later |

### Execution Model
- **Async-first**: Default is submit + poll pattern
- **Sync available**: For dev/interactive use only
- **Idempotency**: Supported via `Idempotency-Key` header
- **Retry Logic**: Max 3 retries, exponential backoff (5s, 30s, 2m)
  - Retry on: timeouts, 429, 5xx
  - No retry on: other 4xx

### Data Flow
```
Client Request
  ↓
FastAPI Endpoint (validate, authenticate)
  ↓
Resolve Active Version (if not specified)
  ↓
Render Template (Jinja2, fail fast on undefined vars)
  ↓
Create Execution Record (status=queued)
  ↓
Enqueue to Redis (Celery task)
  ↓
Worker Picks Up Task
  ↓
Call Provider Adapter (OpenAI)
  ↓
Update Execution Record (status=succeeded/failed)
  ↓
Client Polls for Results
```

---

## 🔀 Dual-Mode Prompt Management (NEW)

### Mode 1: Full Management (Traditional)
**Use Case:** Non-technical teams, dynamic content, frequent updates

**Characteristics:**
- Prompts stored and managed in Prompt Ledger database
- Updates via API/UI without code changes
- Real-time template modifications
- Complete prompt lifecycle management
- Suitable for marketing, content teams

**API Pattern:**
```
PUT /v1/prompts/{name} → Create/Update
GET /v1/prompts/{name} → Retrieve
POST /v1/executions:run → Execute (sync)
POST /v1/executions:submit → Execute (async)
```

### Mode 2: Code-Based Tracking (NEW)
**Use Case:** Developer teams, stable prompts, version control integration

**Characteristics:**
- Prompts defined in application code (constants, config files)
- Prompt Ledger tracks usage and analytics ONLY
- Automatic version detection via template hash comparison
- Git-based version control integration
- Developer-centric workflow
- Unit test friendly (prompts are constants)

**API Pattern:**
```
POST /v1/prompts/register-code → Register code prompts
POST /v1/prompts/{name}/execute → Execute with tracking
GET /v1/prompts/{name}/history?mode=tracking → View history
GET /v1/analytics/prompts?mode=all → Unified analytics
```

**Code Example:**
```python
# In application code (prompts.py)
class Prompts:
    WELCOME = "Hello {{name}}, welcome to {{app}}!"
    ORDER_CONFIRMATION = "Order {{order_id}} confirmed!"

    @classmethod
    def get_template(cls, name):
        return getattr(cls, name)

# On startup or deployment
ledger = PromptLedger(mode="tracking_only")
ledger.register_code_prompts([
    {
        "name": "WELCOME",
        "template_source": Prompts.WELCOME,
        "template_hash": sha256(Prompts.WELCOME)
    },
    {
        "name": "ORDER_CONFIRMATION",
        "template_source": Prompts.ORDER_CONFIRMATION,
        "template_hash": sha256(Prompts.ORDER_CONFIRMATION)
    }
])

# Execute with automatic tracking
result = ledger.execute("WELCOME", {"name": "John", "app": "MyApp"})
```

### Unified Design
**Key Features:**
- **Single table design**: Same tables serve both modes (no duplication)
- **Mode field**: `prompts.mode` ENUM ('full', 'tracking') distinguishes modes
- **Unified execution tracking**: Same `executions` table for both modes
- **Unified analytics**: Single API returns stats across both modes
- **Mode isolation**: Cannot mix operations (validated at API level)

**Benefits:**
- Simple schema (no parallel tables)
- Unified querying and analytics
- Easy migration between modes
- Consistent execution tracking
- Single source of truth

### Mode Selection Criteria

| Factor | Full Management | Code-Based Tracking |
|--------|----------------|-------------------|
| **Team Type** | Mixed/Non-technical | Developer-focused |
| **Update Frequency** | High, dynamic | Low, stable |
| **Version Control** | Database | Git |
| **Testing** | Runtime | Unit testable |
| **Deployment** | No code changes | Code deployment |
| **Use Cases** | Marketing, content | Core app prompts |

---

## 📊 Database Schema (Critical Reference)

### ENUM Types
```sql
prompt_version_status: 'draft' | 'active' | 'deprecated'
execution_mode: 'sync' | 'async'
execution_status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
provider_name: 'openai'
```

### Key Tables
1. **prompts**: Core prompt definitions with active_version_id pointer
   - **NEW: `mode` field** (ENUM: 'full', 'tracking') distinguishes management mode
2. **prompt_versions**: Versioned templates with checksum_hash (unique per prompt)
   - Works for both modes (unified design)
3. **models**: Provider + model configurations
4. **executions**: Execution tracking with full lineage
   - **Unified**: Same table tracks both full and tracking mode executions
5. **execution_inputs**: JSONB variables for each execution

### Critical Constraints
- `UNIQUE(prompt_id, version_number)` - Version numbers sequential
- `UNIQUE(prompt_id, checksum_hash)` - Dedupe by content
- `UNIQUE(prompt_id, idempotency_key)` - Prevent duplicate executions
- Foreign keys with ON DELETE CASCADE where appropriate

### Required Indexes
```sql
idx_exec_prompt_time ON executions(prompt_id, created_at DESC)
idx_exec_version_time ON executions(version_id, created_at DESC)
idx_exec_status_time ON executions(status, created_at DESC)
idx_exec_corr ON executions(correlation_id)
```

---

## 🎨 API Specification (Authoritative)

### Authentication
All endpoints require: `X-API-Key: <internal-key>`

### Core Endpoints

#### 1. Prompt Upsert
```
PUT /v1/prompts/{name}
```
**Critical Logic:**
1. Compute `checksum_hash = sha256(template_source)`
2. If version with same checksum exists: reuse (no new version_number)
3. If checksum is new: create new version with `version_number = max + 1`
4. If `set_active = true`: update `prompts.active_version_id`

#### 2. List Versions
```
GET /v1/prompts/{name}/versions
```

#### 3. Execute Sync
```
POST /v1/executions:run
```
- Inline execution (blocking)
- Returns response immediately
- Mode: `sync`, for dev/interactive use

#### 4. Execute Async (Production Default)
```
POST /v1/executions:submit
```
- Enqueues task, returns execution_id
- Mode: `async`, status: `queued`
- Client polls for results

#### 5. Poll Execution
```
GET /v1/executions/{execution_id}
```
- Returns current status and results (when complete)

### Code-Based Prompt Endpoints (NEW - Section 10 in Spec)

#### 6. Register Code Prompts
```
POST /v1/prompts/register-code
```
**Request:**
```json
{
  "prompts": [
    {
      "name": "WELCOME",
      "template_source": "Hello {{name}}!",
      "template_hash": "abc123..."
    }
  ]
}
```

**Critical Logic:**
1. For each prompt in array:
   - Check if prompt exists by name
   - Compute checksum from template_source
   - If checksum differs from latest version: create new version (increment version_number)
   - If checksum same: return existing version (no new version created)
   - Set `prompts.mode = 'tracking'`
2. Return registration results with change detection

**Response:**
```json
{
  "registered": [
    {
      "name": "WELCOME",
      "mode": "tracking",
      "version": 2,
      "change_detected": true,
      "previous_version": 1
    }
  ]
}
```

#### 7. Execute Code Prompt
```
POST /v1/prompts/{name}/execute
```
- Verify prompt exists and mode='tracking'
- Execute with sync or async mode
- Track execution in unified executions table
- Return execution results with telemetry

#### 8. Get Prompt History (Unified)
```
GET /v1/prompts/{name}/history?mode={full|tracking}
```
- Works for both full and tracking modes
- Returns version history with execution counts
- Include template metadata

#### 9. Unified Analytics
```
GET /v1/analytics/prompts?mode={all|full|tracking}
```
- Aggregate execution stats by mode
- Return total executions, average latency, token usage
- Support mode filtering

**Critical Implementation Notes:**
- **Mode validation**: Cannot execute 'full' mode prompts via code-based endpoints
- **Mode isolation**: Clear error messages for mode mismatches
- **Automatic versioning**: Change detection is automatic based on checksum
- **Unified tracking**: All executions go to same table regardless of mode

---

## 🔧 Development Standards

### Code Style
- **Formatter**: `black` (line length: 88)
- **Import sorter**: `isort`
- **Linter**: `flake8`
- **Type checker**: `mypy` (enforce type hints everywhere)
- Follow PEP 8 conventions

### Documentation
- **Docstrings**: Google style format for all public functions/classes
- **API Docs**: OpenAPI descriptions for all endpoints
- **Comments**: Explain "why", not "what" (code should be self-documenting)

### Error Handling
```python
# ✅ GOOD: Specific exceptions, proper logging
try:
    result = await db.execute(query)
except DatabaseError as e:
    logger.error(f"Database error: {e}", extra={"context": context})
    raise
except ValidationError as e:
    logger.warning(f"Validation failed: {e}")
    raise HTTPException(status_code=400, detail=str(e))

# ❌ BAD: Bare except, no logging
try:
    result = await db.execute(query)
except:
    pass
```

### Async Best Practices
- All I/O operations MUST be async
- Use async context managers: `async with`
- Implement timeouts for external API calls
- Use connection pooling (database, Redis)

### Security Requirements
- **Never commit**: API keys, secrets, passwords, .env files
- **Always validate**: User input at API boundaries
- **Always sanitize**: Data before database operations
- Use environment variables for all configuration
- Follow OWASP security guidelines

---

## 🧪 Testing Standards

### Test Organization
```
tests/
├── unit/              # Fast, isolated, mocked
│   ├── test_models.py
│   ├── test_services.py
│   └── test_utils.py
├── integration/       # Component interactions, test DB
│   ├── test_api.py
│   ├── test_database.py
│   └── test_workers.py
└── e2e/              # Complete workflows
    └── test_workflows.py
```

### Test Naming Convention
```python
# ✅ GOOD: Descriptive, explains scenario
def test_prompt_version_incremented_when_content_changes():
    pass

def test_execution_fails_when_template_has_undefined_variables():
    pass

def test_async_execution_queues_task_and_returns_execution_id():
    pass

# ❌ BAD: Vague, unclear
def test_prompt():
    pass
```

### AAA Pattern (Arrange-Act-Assert)
```python
async def test_checksum_deduplication():
    # Arrange - Set up test data
    template = "Hello {{name}}"
    prompt = await create_prompt("test", template)

    # Act - Execute code under test
    duplicate = await create_prompt_version("test", template)

    # Assert - Verify results
    assert duplicate.version_id == prompt.version_id
    assert duplicate.version_number == prompt.version_number
```

### Testing Requirements
- **Unit tests**: Mock external dependencies (DB, APIs, Redis)
- **Integration tests**: Use test database, real interactions
- **Test doubles**: Factories for data, mocks for external services
- **Cleanup**: Always clean up test data after tests
- **Deterministic**: Tests must not fail randomly

### Test Coverage
- Run: `pytest --cov=src/prompt_ledger --cov-report=html`
- Minimum: 90% overall
- Target: 100% for business logic

---

## 🔄 Git Workflow

### Branch Strategy
```bash
# Feature branches from main
feature/prompt-versioning
feature/async-execution

# Bug fixes
fix/auth-validation
fix/worker-retry-logic

# Hotfixes (critical production issues)
hotfix/security-patch
```

### Commit Format (Conventional Commits)
```bash
type(scope): description

# Examples:
feat(api): add prompt versioning endpoint
fix(worker): handle timeout in async execution
test(models): add checksum deduplication tests
docs(readme): update API examples
refactor(db): optimize execution queries
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `test`: Test additions/updates
- `docs`: Documentation
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `chore`: Maintenance tasks

### Pull Request Requirements
- [ ] All tests pass locally
- [ ] Code coverage maintained (≥90%)
- [ ] Pre-commit hooks pass
- [ ] Self-review completed
- [ ] Tests included for new code
- [ ] Documentation updated
- [ ] Code review approval obtained

---

## 🎯 Implementation-Specific Rules

### Prompt Versioning Logic
```python
# CRITICAL: This is the core versioning algorithm
async def create_or_update_version(
    db: AsyncSession,
    prompt_id: UUID,
    template_source: str,
    set_active: bool = False
) -> PromptVersion:
    """
    1. Compute checksum = sha256(template_source)
    2. Check if version exists with (prompt_id, checksum)
    3. If exists: return existing version
    4. If not: create new with version_number = max + 1
    5. If set_active: update prompts.active_version_id
    """
```

### Rendering Rules
```python
# CRITICAL: Fail fast on undefined variables
from jinja2 import Environment, StrictUndefined

env = Environment(undefined=StrictUndefined)
template = env.from_string(template_source)
try:
    rendered = template.render(**variables)
except UndefinedError as e:
    raise ValidationError(f"Missing variable: {e}")
```

### Worker Contract
```python
# CRITICAL: Worker task structure
@celery_app.task(bind=True, max_retries=3)
async def execute_prompt(self, execution_id: str):
    """
    1. Load execution record from DB
    2. Update status='running', set started_at
    3. Call provider adapter
    4. On success: update response_text, tokens, latency, status='succeeded'
    5. On failure: update error_type, error_message, status='failed'
    6. Set completed_at
    """
```

### Truncation Limits
- **Max rendered_prompt**: 200 KB (truncate, set error_type='truncated')
- **Max response_text**: 500 KB (truncate, set error_type='truncated')

### Code-Based Prompt Registration (NEW)
```python
# CRITICAL: Automatic version detection algorithm
async def register_code_prompts(
    db: AsyncSession,
    prompts: List[CodePromptRegistration]
) -> List[RegistrationResult]:
    """
    For each prompt:
    1. Compute checksum = sha256(template_source)
    2. Check if prompt exists by name
    3. If prompt doesn't exist:
       - Create new prompt with mode='tracking'
       - Create version 1
    4. If prompt exists:
       - Get latest version checksum
       - If checksum differs: create new version (version_number = max + 1)
       - If checksum same: return existing version (no new version)
    5. Return registration result with change_detected flag
    """
```

### Mode Validation (NEW)
```python
# CRITICAL: Enforce mode isolation
async def validate_mode_operation(
    db: AsyncSession,
    prompt_name: str,
    expected_mode: str,
    operation: str
) -> None:
    """
    Validate that operation matches prompt mode.

    Rules:
    - 'full' mode prompts: Can only use traditional PUT/GET endpoints
    - 'tracking' mode prompts: Can only use code-based endpoints
    - Mode mismatch: Raise clear HTTPException with 400 status

    Error messages:
    - "Prompt '{name}' is in full mode. Use PUT /v1/prompts/{name} instead."
    - "Prompt '{name}' is in tracking mode. Use POST /v1/prompts/{name}/execute instead."
    """
    prompt = await get_prompt_by_name(db, prompt_name)
    if prompt and prompt.mode != expected_mode:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt '{prompt_name}' is in {prompt.mode} mode. "
                   f"Cannot perform {operation} operation."
        )
```

---

## 📝 Code Review Checklist

### Before Submitting PR
- [ ] **TDD compliance**: Tests written first, all pass
- [ ] **Coverage**: No decrease, ideally ≥90%
- [ ] **Code style**: black, isort, flake8, mypy all pass
- [ ] **Documentation**: Docstrings updated, API docs current
- [ ] **Self-review**: Reviewed own code for issues
- [ ] **Manual testing**: Tested locally with real scenarios

### Reviewer Checklist
- [ ] **Tests first**: Evidence of TDD (test commits before implementation)
- [ ] **Test quality**: Comprehensive, well-named, proper structure
- [ ] **Functionality**: Code solves problem correctly
- [ ] **Security**: No vulnerabilities, proper validation
- [ ] **Performance**: No obvious bottlenecks
- [ ] **Design**: Follows architecture, maintainable
- [ ] **Documentation**: Clear, complete, accurate

### Review Etiquette
- **Be constructive**: Explain reasoning, provide examples
- **Be respectful**: Focus on code, not person
- **Be thorough**: Check all aspects, not just syntax
- **Acknowledge**: Recognize good work and improvements

---

## 🚀 MVP Definition of Done

The system is complete when ALL of these work:

### Full Management Mode (Traditional)

1. ✅ **Prompt registration and versioning**
   - Create new prompt via API
   - Update prompt creates new version only if content changed
   - Same content reuses existing version (checksum dedupe)
   - Active version pointer works correctly

2. ✅ **Active version resolution**
   - Execute without version uses active version
   - Execute with specific version_number works

3. ✅ **Async execution flow**
   - Submit creates execution record (status=queued)
   - Task enqueued to Redis
   - Worker picks up and executes
   - Status updated to succeeded/failed

4. ✅ **Polling returns results**
   - Can poll execution status
   - Returns response when complete
   - Includes telemetry (tokens, latency)

5. ✅ **Full traceability**
   - Can query executions by prompt
   - Can query executions by version
   - Can trace lineage: execution → version → prompt

6. ✅ **Idempotency works**
   - Same idempotency_key returns existing execution
   - No duplicate executions created

7. ✅ **OpenAI adapter end-to-end**
   - Real API call succeeds
   - Response captured correctly
   - Token counting accurate
   - Latency measured

### Code-Based Tracking Mode (NEW)

8. 🆕 **Code prompt registration with automatic versioning**
   - Register multiple prompts via POST /v1/prompts/register-code
   - First registration creates version 1 with mode='tracking'
   - Re-registration with same content: no new version (checksum dedupe)
   - Re-registration with changed content: new version created automatically
   - Registration response includes change_detected flag

9. 🆕 **Automatic change detection works correctly**
   - Checksum comparison detects content changes
   - Version number auto-increments on change
   - Version reused when content unchanged
   - Version history preserved

10. 🆕 **Code-based execution works**
    - Execute tracking mode prompt (sync) via POST /v1/prompts/{name}/execute
    - Execute tracking mode prompt (async)
    - Execution tracked in unified executions table
    - Telemetry captured (tokens, latency)

11. 🆕 **Mode isolation enforced**
    - Cannot execute full mode prompt via code-based endpoints
    - Cannot execute tracking mode prompt via traditional PUT
    - Clear error messages for mode mismatches (400 status)
    - Mode validation happens before execution

12. 🆕 **Unified analytics work across both modes**
    - GET /v1/analytics/prompts?mode=all returns combined stats
    - Can filter by mode (full, tracking, all)
    - Stats include: execution counts, latency, tokens by mode
    - Prompt counts by mode

13. 🆕 **Prompt history works for both modes**
    - GET /v1/prompts/{name}/history?mode=full returns full mode history
    - GET /v1/prompts/{name}/history?mode=tracking returns tracking mode history
    - History includes: version metadata, execution counts, template content
    - Version chronology preserved

### Integration & Cross-Mode

14. 🆕 **Mixed mode operations work correctly**
    - Can have both full and tracking mode prompts in same system
    - Analytics correctly aggregates across modes
    - No data contamination between modes
    - Database queries efficient for both modes

---

## 🛠️ Common Development Tasks

### Running Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=src/prompt_ledger --cov-report=html

# Specific test file
pytest tests/unit/test_models.py

# Specific test
pytest tests/unit/test_models.py::test_prompt_version_creation

# Watch mode (run on file changes)
pytest-watch
```

### Code Quality Checks
```bash
# Format code
black src/ tests/
isort src/ tests/

# Check formatting (CI mode)
black --check src/ tests/
isort --check-only src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/
```

### Database Operations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Running Services
```bash
# Start dependencies (Postgres, Redis)
docker-compose up -d postgres redis

# Start API server (development)
.venv/Scripts/uvicorn prompt_ledger.api.main:app --reload

# Start Celery worker
.venv/Scripts/celery -A prompt_ledger.workers.celery_app worker --loglevel=info

# Full stack with Docker
docker-compose up -d
```

---

## ⚠️ Common Pitfalls to Avoid

### 1. Writing Code Before Tests
```python
# ❌ WRONG: Writing implementation first
def create_prompt_version(...):
    # implementation here
    pass

# ✅ RIGHT: Write test first
def test_create_prompt_version_increments_number():
    # Arrange
    prompt = create_prompt("test", "v1")
    # Act
    new_version = create_prompt_version("test", "v2")
    # Assert
    assert new_version.version_number == 2
```

### 2. Ignoring Error Cases
```python
# ❌ WRONG: Only happy path
def test_execution():
    result = execute_prompt(valid_data)
    assert result.status == "succeeded"

# ✅ RIGHT: Test errors too
def test_execution_fails_on_invalid_template():
    with pytest.raises(ValidationError):
        execute_prompt(invalid_template)
```

### 3. Using Bare Excepts
```python
# ❌ WRONG: Swallowing all errors
try:
    result = await db.execute(query)
except:
    return None

# ✅ RIGHT: Specific exceptions
try:
    result = await db.execute(query)
except DatabaseError as e:
    logger.error(f"DB error: {e}")
    raise
```

### 4. Forgetting Async/Await
```python
# ❌ WRONG: Blocking I/O
def get_prompt(db, name):
    return db.execute(query).scalar()

# ✅ RIGHT: Async I/O
async def get_prompt(db: AsyncSession, name: str):
    result = await db.execute(query)
    return result.scalar_one_or_none()
```

### 5. Hardcoding Configuration
```python
# ❌ WRONG: Hardcoded values
OPENAI_API_KEY = "sk-1234567890"
DATABASE_URL = "postgresql://localhost/db"

# ✅ RIGHT: Environment variables
from .settings import settings

api_key = settings.openai_api_key
db_url = settings.database_url
```

### 6. Ignoring Mode Validation (NEW)
```python
# ❌ WRONG: Not checking prompt mode
async def execute_code_prompt(name: str, variables: dict):
    prompt = await get_prompt_by_name(db, name)
    # No mode check - could execute full mode prompt!
    return await execute(prompt, variables)

# ✅ RIGHT: Validate mode before execution
async def execute_code_prompt(name: str, variables: dict):
    prompt = await get_prompt_by_name(db, name)
    if prompt.mode != 'tracking':
        raise HTTPException(
            status_code=400,
            detail=f"Prompt '{name}' is in {prompt.mode} mode. "
                   f"Use code-based execute endpoint."
        )
    return await execute(prompt, variables)
```

---

## 📚 Reference Documentation

### Internal Documents
- **PromptLedger Spec.md**: Complete technical specification
- **TODO.md**: Implementation checklist and priorities
- **rules/development.md**: Full development guidelines
- **rules/tdd.md**: Comprehensive TDD rules
- **rules/code-review.md**: Review process details
- **rules/git-workflow.md**: Git and branching standards

### Key Files
- **src/prompt_ledger/api/main.py**: FastAPI application entry
- **src/prompt_ledger/models/**: SQLAlchemy models
- **src/prompt_ledger/services/**: Business logic layer
- **src/prompt_ledger/workers/**: Celery tasks
- **alembic/versions/**: Database migrations
- **tests/**: Test suite

### External Resources
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Celery Documentation](https://docs.celeryq.dev/)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [Pytest Documentation](https://docs.pytest.org/)

---

## 🎓 Development Mindset

### Always Remember
1. **Tests first, always** - No exceptions to TDD
2. **Dual-mode architecture** - Always validate prompt mode before operations
3. **Fail fast** - Catch errors early, don't hide them
4. **Be explicit** - Type hints, clear names, good docs
5. **Keep it simple** - Don't over-engineer
6. **Async everywhere** - This is an async-first system
7. **Security matters** - Validate, sanitize, protect
8. **Performance counts** - Index, cache, optimize
9. **Observability** - Log, measure, trace
10. **Mode isolation** - Enforce strict boundaries between full and tracking modes

### When in Doubt
1. **Read the spec** - PromptLedger Spec.md is authoritative
2. **Check the rules** - TDD and development standards
3. **Look at existing code** - Follow established patterns
4. **Write a test** - Let TDD guide your design
5. **Ask questions** - Better to clarify than assume

---

## ✅ Quick Pre-Flight Checklist

Before starting ANY development work:
- [ ] Virtual environment activated (Python 3.11.2)
- [ ] Latest code pulled from `main`
- [ ] All dependencies installed (`pip install -e ".[dev]"`)
- [ ] Database migrations applied (`alembic upgrade head`)
- [ ] Docker services running (Postgres, Redis)
- [ ] All tests passing (`pytest`)
- [ ] Pre-commit hooks installed (`pre-commit install`)

Before committing ANY code:
- [ ] Tests written FIRST (TDD compliance)
- [ ] All tests passing locally
- [ ] Code formatted (black, isort)
- [ ] Linting clean (flake8)
- [ ] Type checking clean (mypy)
- [ ] Coverage maintained (≥90%)
- [ ] Documentation updated
- [ ] Self-review completed

---

**Remember: Quality is not negotiable. These rules exist to ensure we build a robust, maintainable, professional system.**

**TDD is the foundation. Testing is not optional. Code without tests is broken by definition.**
