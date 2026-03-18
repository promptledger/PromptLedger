# PromptLedger Architecture

## Overview

PromptLedger is a production-grade prompt management and observability platform for LLM applications. This document describes the system architecture, design decisions, and technical implementation.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Applications                       │
│         (Python SDK, REST API, Direct HTTP Requests)             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Prompts    │  │  Executions  │  │  Analytics   │          │
│  │   Endpoint   │  │   Endpoint   │  │   Endpoint   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                   │
│         ▼                  ▼                  ▼                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │         Service Layer (Business Logic)           │            │
│  │  - PromptService  - ExecutionService             │            │
│  │  - ProviderAdapter Factory                       │            │
│  └─────────────────┬─────────────────┬─────────────┘            │
└────────────────────┼─────────────────┼──────────────────────────┘
                     │                  │
         ┌───────────▼──────────┐      │
         │   PostgreSQL DB      │      │
         │  ┌────────────────┐  │      │
         │  │    prompts     │  │      │
         │  │prompt_versions │  │      │
         │  │   executions   │  │      │
         │  │     spans      │  │      │
         │  │     models     │  │      │
         │  └────────────────┘  │      │
         └──────────────────────┘      │
                                       │
                          ┌────────────▼──────────┐
                          │     Redis Queue       │
                          │  (Celery Broker)      │
                          └────────────┬──────────┘
                                       │
                          ┌────────────▼──────────┐
                          │   Celery Workers      │
                          │  ┌─────────────────┐  │
                          │  │ Async Execution │  │
                          │  │     Tasks       │  │
                          │  └────────┬────────┘  │
                          └─────────────┼──────────┘
                                       │
                          ┌────────────▼──────────┐
                          │  Provider Adapters    │
                          │  ┌─────────────────┐  │
                          │  │ OpenAI Adapter  │  │
                          │  │(Anthropic, etc) │  │
                          │  └────────┬────────┘  │
                          └─────────────┼──────────┘
                                       │
                          ┌────────────▼──────────┐
                          │   LLM Providers       │
                          │   (OpenAI API, etc)   │
                          └───────────────────────┘
```

## Core Components

### 1. API Layer (FastAPI)

**Responsibilities:**
- HTTP request handling
- Input validation (Pydantic models)
- Authentication/authorization
- Response formatting

**Key Endpoints:**
- `PUT /v1/prompts/{name}` - Create/update prompts (full mode)
- `POST /v1/prompts/register-code` - Register code prompts (tracking mode)
- `POST /v1/executions/run` - Synchronous execution
- `POST /v1/executions/submit` - Asynchronous execution
- `GET /v1/analytics/*` - Analytics and metrics
- `POST /v1/admin/projects` - Create named projects and issue scoped API keys

**Technology:**
- FastAPI (async Python web framework)
- Pydantic for request/response validation
- Async/await throughout

### 2. Service Layer

**PromptService:**
- Prompt CRUD operations
- Version management
- Content-based deduplication
- Mode validation (full vs tracking)

**ExecutionService:**
- Execution lifecycle management
- Template rendering (Jinja2)
- Provider routing
- Telemetry collection

**ProviderAdapter:**
- Abstract interface for LLM providers
- OpenAI implementation (others extensible)
- Retry logic with exponential backoff
- Token counting and cost tracking

### 3. Data Layer

**PostgreSQL Database:**

**Core Tables:**
```sql
projects (Epic 2: Multi-Tenancy)
├── project_id (PK, UUID)
├── name (unique text)
└── created_at

api_keys (Epic 2: Multi-Tenancy)
├── key_id (PK, UUID)
├── key_hash (SHA-256 of plaintext, unique — plaintext never stored)
├── project_id (FK → projects)
├── label (text, human-readable identifier)
├── is_system_key (bool — seeded env-var keys; cannot be deleted)
└── created_at

prompts
├── prompt_id (PK, UUID)
├── project_id (FK → projects — all prompts scoped to one project)
├── name (unique within project via uq_project_prompt_name)
├── mode (enum: 'full', 'tracking')
├── description, owner_team
├── active_version_id (FK)
└── timestamps

prompt_versions
├── version_id (PK, UUID)
├── prompt_id (FK)
├── version_number (int)
├── template_source (text)
├── checksum_hash (sha256, unique per prompt)
├── status (enum: 'active', 'draft', 'archived')
├── created_by
└── created_at

executions
├── execution_id (PK, UUID)
├── project_id (FK → projects — scoped to calling project)
├── prompt_id (FK), version_id (FK), model_id (FK)
├── execution_mode (enum: 'sync', 'async')
├── status (enum: 'queued', 'running', 'succeeded', 'failed')
├── rendered_prompt (text), messages_json (JSONB)
├── response_text (text)
├── telemetry (prompt_tokens, response_tokens, latency_ms)
├── correlation_id, idempotency_key (unique per prompt)
└── timestamps

spans
├── span_id (PK, UUID)
├── project_id (FK → projects — scoped to calling project)
├── trace_id (string, indexed)
├── parent_span_id (FK, self-referential)
├── execution_id (FK, nullable — 1:1 with Execution when auto-created)
├── name, kind, agent_id, prompt_name
├── start_time, end_time, duration_ms
├── status, error_message
├── input_data, output_data (JSONB)
├── model, prompt_tokens, completion_tokens
└── attributes (JSONB)

models
├── model_id (PK, UUID)
├── provider (string)
├── model_name (string)
├── max_tokens, supports_streaming
└── created_at
```

**Epic 2 namespacing additions:**
- `projects` and `api_keys` are now part of the data model
- `prompts` are scoped by `project_id`
- `executions` and `spans` also carry `project_id`, which is what isolates traces and analytics per project

**Key Design Decisions:**

1. **Unified Schema for Dual Modes**
   - Single `prompts` table with `mode` column
   - Same execution tracking regardless of source
   - Simplified analytics and reporting

2. **Project Namespacing (Epic 2)**
   - `projects` is a first-class tenant table
   - `api_keys` stores SHA-256 hashes only; plaintext keys are returned once and discarded
   - `prompts` are unique by `(project_id, name)` rather than globally
   - `executions` and `spans` carry `project_id` so traces and analytics are isolated per project

3. **Content-Based Versioning**
   - SHA-256 checksum on `template_source`
   - Unique constraint: `(prompt_id, checksum_hash)`
   - Automatic deduplication
   - Version increment only on content change

4. **Idempotency & Correlation**
   - `idempotency_key`: Prevent duplicate executions
   - `correlation_id`: Link related executions across workflows

5. **JSONB for Flexibility**
   - `execution_inputs.variables_json`: Arbitrary input variables
   - `spans.attributes`: Workflow-specific metadata
   - Balance between schema and flexibility

### 4. Async Execution Pipeline

**Components:**
- **Redis**: Message broker and result backend
- **Celery**: Task queue framework
- **Workers**: Process async execution tasks

**Flow:**
1. Client submits execution via `/executions/submit`
2. API creates execution record (status: `queued`)
3. Task pushed to Redis queue
4. Celery worker picks up task
5. Worker executes prompt via provider
6. Worker updates execution record (status: `succeeded`/`failed`)
7. Client polls `/executions/{id}` for result

**Benefits:**
- Non-blocking API responses
- Scalable worker pool
- Retry logic with exponential backoff
- Production-grade reliability

### 5. Provider Abstraction

**Abstract Base Class:**
```python
class ProviderAdapter(ABC):
    @abstractmethod
    async def generate(
        self,
        rendered_prompt: str,
        model_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Returns:
        {
            "response_text": str,
            "prompt_tokens": int,
            "response_tokens": int,
            "latency_ms": int
        }
        """
```

**Current Implementation:**
- OpenAI (GPT-4, GPT-3.5, etc.)

**Future:**
- Anthropic (Claude)
- Google (Gemini)
- Cohere
- Local models (Ollama)

**Factory Pattern:**
```python
ProviderAdapterFactory.create(provider="openai")
```

## Design Patterns

### 1. Repository Pattern
- Services interact with repositories
- Repositories encapsulate database access
- Easy to mock for testing

### 2. Factory Pattern
- `ProviderAdapterFactory` for provider instantiation
- Extensible without modifying core code

### 3. Strategy Pattern
- Different execution strategies (sync vs async)
- Different prompt management modes (full vs tracking)

### 4. Template Method
- Base execution flow is consistent
- Provider-specific logic encapsulated in adapters

## Dual-Mode Architecture

### Full Management Mode

**Characteristics:**
- Prompts stored in database
- API-driven CRUD operations
- Real-time updates without code deployment
- Manual versioning (set_active flag)

**Use Cases:**
- Marketing teams managing email templates
- Non-technical users
- High-velocity content changes
- A/B testing

**Workflow:**
```
User → PUT /v1/prompts/{name} → DB
User → POST /v1/executions/run → Execute
```

### Code-Based Tracking Mode

**Characteristics:**
- Prompts defined in application code
- Git-managed version history
- Automatic version detection via checksum
- Registration on app startup

**Use Cases:**
- Engineering teams
- Stable prompts in production code
- CI/CD integration
- Unit testable prompts

**Workflow:**
```
Code → POST /v1/prompts/register-code → Hash check → DB
App → POST /v1/prompts/{name}/execute → Execute
```

### Mode Isolation

**Validation:**
- API endpoints check prompt mode
- Error if wrong endpoint for mode
- Clear error messages guide users

**Example:**
```python
if prompt.mode == "tracking" and endpoint == "PUT /v1/prompts/{name}":
    raise HTTPException(400, "Use code-based endpoints for tracking mode")
```

## Workflow Tracking (FR-001)

### Span Model

**Based on OpenTelemetry:**
- `trace_id`: Groups all operations in a workflow run
- `parent_span_id`: Links child operations to parents
- `span_id`: Unique identifier for this operation

**Supported Patterns:**

1. **Linear Chains:**
   ```
   Span1 → Span2 → Span3 → Span4
   ```

2. **Parallel Fan-out:**
   ```
           ├→ Span2
   Span1 → ├→ Span3 → Span5
           └→ Span4
   ```

3. **Nested Agents:**
   ```
   Agent1
   ├── Step1
   ├── Agent2 (sub-agent)
   │   ├── SubStep1
   │   └── SubStep2
   └── Step2
   ```

4. **ReAct Loops:**
   ```
   Reason1 → Act1 → Observe1 → Reason2 → Act2 → ...
   ```

### External Call Logging

**Capability:**
- Track non-PromptLedger LLM calls
- Log tool calls (search, database, APIs)
- Complete workflow visibility

**Example:**
```python
# Direct OpenAI call (not via PromptLedger)
span = create_span(
    trace_id="workflow-123",
    name="direct_openai_call",
    kind="llm.generation",
    input_data={"prompt": "..."},
    model="gpt-4"
)
```

## Security Considerations

### Current Implementation

**API Key Authentication:**
- Header: `X-API-Key`
- Service env var: `API_KEY` seeds the `"default"` project's system key at startup
- Consuming applications should use project-scoped keys issued via `POST /v1/admin/projects`
- Plaintext keys are SHA-256 hashed before lookup and are never stored directly

**Request auth flow:**
1. Read `X-API-Key`
2. Compute SHA-256 hash of the presented key
3. Check the in-memory TTL cache (60 seconds)
4. On cache miss, look up the hash in `api_keys`
5. Resolve the key's `project_id` and scope downstream prompt/execution/span/analytics queries to that project

**Admin authorization:**
- `/v1/admin/*` endpoints require the authenticated key to belong to the `"default"` project
- non-default project keys receive `403 Forbidden` on admin endpoints
- system keys (`is_system_key = true`) cannot be deleted; operators rotate them by updating `API_KEY` and restarting the service

**Recommendations for Production:**

1. **Use strong, randomly-generated keys**
   ```bash
   openssl rand -hex 32
   ```

2. **Use zero-downtime key rotation**
   - Issue a replacement project key first
   - Update the consuming application
   - Revoke the old key only after the new key is confirmed working

3. **Add rate limiting**
   - Per-key request limits
   - Prevent abuse

4. **Future: RBAC**
   - Team-based access control
   - Prompt ownership rules
   - Execution policies

### Data Privacy

**Sensitive Data:**
- Prompt templates may contain business logic
- Execution inputs may contain PII
- LLM responses may contain sensitive content

**Recommendations:**
1. Encrypt database at rest
2. Use TLS for all connections
3. Implement data retention policies
4. PII detection and masking
5. Audit logging for compliance

## Scalability Considerations

### Current Bottlenecks

1. **Database:** Single PostgreSQL instance
2. **Workers:** Limited by Celery worker count
3. **Redis:** Single Redis instance

### Scaling Strategies

**Horizontal Scaling:**

1. **API Layer:**
   - Stateless FastAPI instances
   - Load balancer (nginx, HAProxy)
   - Auto-scaling based on traffic

2. **Workers:**
   - Increase Celery worker count
   - Separate queues for priority
   - Multiple worker pools

3. **Database:**
   - Read replicas for analytics queries
   - Connection pooling (PgBouncer)
   - Partitioning for large tables

4. **Redis:**
   - Redis Cluster for high availability
   - Separate broker and result backend

**Performance Optimizations:**

1. **Caching:**
   - Cache active prompt versions
   - Cache model configurations
   - Use Redis for session data

2. **Database Indexing:**
   - Already indexed: prompt_id, version_id, status, timestamps
   - Composite indexes for common queries
   - Partial indexes for specific use cases

3. **Query Optimization:**
   - Eager loading for relationships
   - Pagination for list endpoints
   - Aggregation pushdown to database

## Monitoring & Observability

### Current Implementation

**Health Checks:**
- `GET /health` endpoint
- Database connectivity check
- Redis connectivity check

**Logging:**
- Structured logging (JSON)
- Log levels (DEBUG, INFO, WARNING, ERROR)
- Request/response logging

**Telemetry:**
- Execution latency
- Token counts
- Error rates

### Recommended Additions

1. **Metrics (Prometheus):**
   - Request rate, latency, errors
   - Queue depth, worker utilization
   - Database connection pool stats

2. **Tracing (Jaeger/DataDog):**
   - Distributed tracing
   - Span export from internal tracking

3. **Alerting:**
   - High error rates
   - Queue backlog
   - Database performance degradation

## Testing Strategy

### Current Coverage

**Unit Tests:**
- Model tests (prompt, execution, span)
- Service layer tests
- Utility function tests

**Integration Tests:**
- API endpoint tests
- Database interaction tests
- End-to-end workflows

**Test Infrastructure:**
- pytest framework
- Fixtures for database setup
- Mock LLM providers for testing

### TDD Approach

1. Write failing test
2. Implement minimal code
3. Refactor while keeping tests green

**Coverage Target:** 90%+

## Deployment

### Docker Compose (Development)

**Services:**
- `api`: FastAPI application
- `worker`: Celery worker
- `beat`: Celery beat scheduler
- `postgres`: PostgreSQL database
- `redis`: Redis broker/backend

### Production Deployment

**Recommended:**

1. **Container Orchestration:**
   - Kubernetes (GKE, EKS, AKS)
   - Docker Swarm (simpler alternative)

2. **Managed Services:**
   - Managed PostgreSQL (RDS, Cloud SQL)
   - Managed Redis (ElastiCache, Memorystore)

3. **CI/CD:**
   - GitHub Actions for testing
   - Docker image builds
   - Automated deployment

4. **Infrastructure as Code:**
   - Terraform for cloud resources
   - Helm charts for Kubernetes

## Trade-offs & Design Decisions

### 1. Async-First vs Sync-First

**Decision:** Async-first with sync fallback

**Reasoning:**
- Production workloads require non-blocking execution
- Sync mode useful for development/testing
- Celery provides production-grade reliability

**Trade-off:**
- More complex infrastructure
- Worth it for scalability

### 2. Unified Schema vs Separate Tables

**Decision:** Unified schema for both modes

**Reasoning:**
- Simplified analytics across modes
- Easier to migrate between modes
- Reduced code duplication

**Trade-off:**
- Some columns unused per mode
- Acceptable for flexibility gained

### 3. Content-Based vs Timestamp Versioning

**Decision:** Content-based (checksum hashing)

**Reasoning:**
- Automatic deduplication
- Deterministic versioning
- Reproducible research

**Trade-off:**
- Slightly more complex logic
- Worthwhile for accuracy

### 4. OpenTelemetry Alignment

**Decision:** Align span model with OTel standards

**Reasoning:**
- Industry standard
- Future APM integrations
- Familiar to ops teams

**Trade-off:**
- More flexible schema (JSONB)
- Acceptable for extensibility

## Future Enhancements

### Short-term (3-6 months)
- [ ] Multi-provider support (Anthropic, Google)
- [ ] Prompt evaluation framework
- [ ] A/B testing infrastructure
- [ ] Web dashboard (React/Next.js)

### Medium-term (6-12 months)
- [ ] RBAC and multi-tenancy
- [ ] Cost tracking and budgeting
- [ ] Prompt optimization suggestions (RAG, few-shot)
- [ ] Integration with APM tools (DataDog, Jaeger)

### Long-term (12+ months)
- [ ] Prompt marketplace
- [ ] Auto-scaling based on usage
- [ ] ML-based prompt improvement
- [ ] Federated learning for prompt optimization

---

## References

- FastAPI Documentation: https://fastapi.tiangolo.com
- Celery Documentation: https://docs.celeryproject.org
- OpenTelemetry Specification: https://opentelemetry.io
- SQLAlchemy Documentation: https://docs.sqlalchemy.org

---

*Last Updated: 2026-03-18*
*Architecture Version: 2.0 — Epic 2: project namespacing, DB-backed API keys, admin API*
