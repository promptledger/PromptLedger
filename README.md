# Prompt Ledger

PromptLedger is an open-source prompt registry and execution framework designed
to solve **prompt sprawl** in GenAI and agentic AI systems.

As GenAI applications scale, prompts become scattered across code, notebooks,
configs, and experiments—making them hard to govern, reproduce, and audit.
PromptLedger provides a centralized control plane for managing prompt versions,
executions, and lineage, giving teams observability and governance without
slowing down development.

📖 Background: [The Hidden Crisis of Prompt Sprawl](<https://medium.com/@martin_rodek/the-hidden-crisis-of-prompt-sprawl-and-how-to-fix-it-9b5e65cd10fc>)


## Features

- **Dual-Mode Prompt Management**: Full database management OR code-based tracking with automatic versioning
- **Unified `execute()` Method**: Single SDK call for Mode 1 and Mode 2 — PromptLedger makes the LLM call, creates the span, and returns `response_text` + `span_id`. No provider SDK in your application code.
- **Workflow Execution Tracking**: OpenTelemetry-style spans for tracing multi-step agentic workflows
- **Prompt Registry**: Content-based versioning with SHA-256 deduplication
- **Multi-Provider Execution**: OpenAI and Anthropic adapters with extensible factory pattern
- **Multi-Provider Cost Model**: YAML-backed pricing table with fnmatch glob matching; `total_cost` in analytics and trace summaries
- **Python SDK**: `pip install promptledger-client` — `AsyncPromptLedgerClient`, `execute()`, contextvars trace helpers, Pydantic models
- **Dry-Run Registration**: `POST /v1/prompts/register-code` with `dry_run: true` for CI/CD validation
- **Async-first Design**: Redis + Celery for production workloads
- **Full Lineage**: Complete execution tracking and parent-child relationships in Postgres
- **API Key Auth**: `X-API-Key` header enforced on all `/v1/*` endpoints

## Architecture

```
Client (Agentic Workflow)
  │
  ├─► Mode 1: POST /v1/executions/run ─► Provider Adapter (OpenAI / Anthropic)
  │           (prompt_name + variables)         │
  │                                             ▼
  │                                      Results + Span + Telemetry → Postgres
  │
  ├─► Mode 2: POST /v1/executions/run ─► Provider Adapter (OpenAI / Anthropic)
  │           (prompt_name + messages)          │
  │           client constructs messages,        ▼
  │           PL makes the LLM call      Results + Span + Telemetry → Postgres
  │
  └─► Low-level: POST /v1/spans ───────► Postgres (spans, traces)
                 (phase spans, guardrail child spans, tool calls)

Prompt Registry & Execution API (FastAPI)
  ├── Registry ops   → Postgres (prompts, versions)
  ├── Span tracking  → Postgres (traces, parent-child tree)
  └── Submit async   → Redis → Celery Worker → Provider Adapter
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd prompt-ledger
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start with Docker Compose**
   ```bash
   docker-compose up -d
   ```

4. **Initialize database**
   ```bash
   # Run database migrations
   docker-compose exec api alembic upgrade head

   # Seed initial models (optional)
   docker-compose exec api python -m prompt_ledger.scripts.seed_models
   ```

### Development Setup

1. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

2. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

3. **Start local services**
   ```bash
   # Start PostgreSQL and Redis
   docker-compose up -d postgres redis

   # Run migrations
   alembic upgrade head

   # Start API server
   uvicorn prompt_ledger.api.main:app --reload

   # Start worker (in separate terminal)
   celery -A prompt_ledger.workers.celery_app worker --loglevel=info
   ```

## API Usage

### Authentication

All endpoints require an API key:
```
X-API-Key: <your-api-key>
```

### Prompt Management

**Create/Update Prompt**
```bash
curl -X PUT "http://localhost:8000/v1/prompts/doc_summarizer" \
  -H "X-API-Key: dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Summarize documents",
    "owner_team": "AI-Platform",
    "template_source": "Summarize:\n{{text}}",
    "created_by": "martin",
    "set_active": true
  }'
```

**Get Prompt**
```bash
curl -X GET "http://localhost:8000/v1/prompts/doc_summarizer" \
  -H "X-API-Key: dev-key-change-in-production"
```

**List Versions**
```bash
curl -X GET "http://localhost:8000/v1/prompts/doc_summarizer/versions" \
  -H "X-API-Key: dev-key-change-in-production"
```

### Execution

**Synchronous Execution**
```bash
curl -X POST "http://localhost:8000/v1/executions:run" \
  -H "X-API-Key: dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt_name": "doc_summarizer",
    "environment": "dev",
    "variables": {"text": "Your document text here..."},
    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
    "params": {"max_new_tokens": 800, "temperature": 0.2}
  }'
```

**Asynchronous Execution**
```bash
curl -X POST "http://localhost:8000/v1/executions:submit" \
  -H "X-API-Key: dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt_name": "doc_summarizer",
    "environment": "dev",
    "variables": {"text": "Your document text here..."},
    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
    "params": {"max_new_tokens": 800, "temperature": 0.2}
  }'
```

**Poll Execution Status**
```bash
curl -X GET "http://localhost:8000/v1/executions/{execution_id}" \
  -H "X-API-Key: dev-key-change-in-production"
```

## Workflow Execution Tracking (Mode 2)

For teams that call LLM providers directly, use `POST /v1/spans` to report each call
and `GET /v1/traces/{trace_id}/summary` to view aggregated cost and token usage.

```python
import os, time, anthropic, httpx
from datetime import datetime, timezone

API_URL = os.environ["PROMPTLEDGER_API_URL"]
HEADERS = {"X-API-Key": os.environ["PROMPTLEDGER_API_KEY"]}

trace_id = "trace-my-workflow-001"

# Your application calls the LLM directly
client = anthropic.Anthropic()
start = time.time()
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=512,
    messages=[{"role": "user", "content": "Summarize this paper: ..."}],
)
duration_ms = int((time.time() - start) * 1000)

# Report the span to PromptLedger
httpx.post(
    f"{API_URL}/v1/spans",
    headers=HEADERS,
    json={
        "trace_id": trace_id,
        "name": "paper_agent.extraction",
        "kind": "llm.generation",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "status": "ok",
        "model": "claude-haiku-4-5-20251001",
        "prompt_tokens": response.usage.input_tokens,
        "completion_tokens": response.usage.output_tokens,
        "prompt_name": "paper_agent.extraction",
    },
)

# View aggregated cost for the trace
summary = httpx.get(f"{API_URL}/v1/traces/{trace_id}/summary", headers=HEADERS).json()
print(f"Total cost: ${summary['total_cost']}")
print(f"Tokens: {summary['total_prompt_tokens']} in / {summary['total_completion_tokens']} out")
```

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for the full Mode 2 walkthrough,
including the `promptledger-client` SDK, `contextvars` trace propagation,
CI/CD dry-run recipe, and the guardrail alert pattern.

## Dual-Mode Prompt Management

| | Mode 1 — Full Management | Mode 2 — Code-Based Tracking |
|---|---|---|
| Prompts live in | PromptLedger database | Your code / Git |
| LLM calls made by | PromptLedger execution engine | Your application |
| Provider support | OpenAI, Anthropic | Any provider |
| Best for | Non-technical editors, A/B tests | Developer-owned, Git-first |

### Mode 1 quick example

```bash
# Create a prompt
curl -X PUT "$API_URL/v1/prompts/doc_summarizer" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"template_source":"Summarize:\n{{text}}","set_active":true}'

# Execute it (PromptLedger calls the LLM)
curl -X POST "$API_URL/v1/executions:run" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"prompt_name":"doc_summarizer","variables":{"text":"..."},
       "model":{"provider":"anthropic","model_name":"claude-haiku-4-5-20251001"}}'
```

### Mode 2 quick example

```bash
# Register code prompts (idempotent, content-based versioning)
curl -X POST "$API_URL/v1/prompts/register-code" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"prompts":[{"name":"summarizer","template_source":"Summarize: {{text}}",
       "template_hash":"<sha256>"}]}'

# Dry-run to check for unregistered changes (CI/CD gate)
curl -X POST "$API_URL/v1/prompts/register-code" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"prompts":[...],"dry_run":true}'
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | `postgresql+asyncpg://postgres:password@localhost:5432/prompt_ledger` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `API_KEY` | Internal API key for authentication | `dev-key-change-in-production` |
| `DEBUG` | Enable debug mode | `false` |

### Database Schema

The service uses a unified table design that supports both dual-mode prompts and workflow tracking:

**Core Tables:**
- `prompts` - Prompt definitions with mode indicator ('full' or 'tracking')
- `prompt_versions` - Versioned prompt templates with checksums
- `executions` - Unified execution tracking for both modes
- `spans` - Workflow execution tracking with trace_id and parent-child relationships
- `models` - AI model configurations
- `execution_inputs` - Input variables for each execution

**Workflow Tracking:**
- `spans.trace_id` groups all operations in a workflow run
- `spans.parent_span_id` creates nested operation trees
- `spans.execution_id` links spans to prompt executions (when applicable)
- Supports tracking both PromptLedger executions and external LLM calls

**Mode Differentiation:**
- `prompts.mode` field distinguishes between 'full' and 'tracking' modes
- Same tables serve both modes - no duplication needed
- Unified analytics across all prompt types and workflow patterns

**Benefits:**
- Single source of truth for all prompt data and workflow traces
- Unified analytics and reporting across modes and workflows
- OpenTelemetry-compatible design for industry-standard observability
- Simplified maintenance and migrations
- Easy querying across modes and workflow patterns

See the [design specification](PromptLedger Spec.md) for complete schema details.

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src/ tests/
isort src/ tests/
```

### Type Checking

```bash
mypy src/
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Production Deployment

### Docker Deployment

1. **Build and deploy**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

2. **Configure environment variables**
   - Set strong API keys
   - Use production database URLs
   - Configure monitoring and logging

3. **Scale workers**
   ```bash
   docker-compose up -d --scale worker=3
   ```

### Monitoring

- Health check: `GET /health`
- Application logs available via Docker logs
- Consider adding Prometheus metrics for production

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Roadmap

### Epic 1 — Integration Enhancements ✅ (in progress)
- [x] Story 1.0 — API key auth (`X-API-Key` enforced on all `/v1/*` endpoints)
- [x] Story 1.1 — Anthropic provider adapter (`claude-haiku-4-5-*`, `claude-sonnet-4-6*`, `claude-opus-4-6*`)
- [x] Story 1.3 — `register-code` dry-run and change detection
- [x] Story 1.4 — Multi-provider cost model (YAML pricing table, `total_cost` in analytics)
- [x] Story 1.6 — Code-Based Tracking integration guide (this section)
- [x] Story 1.8 — Execution telemetry (`model_name`, `provider`, `total_cost` in execution responses)
- [ ] Story 1.2 — Official Python SDK (`pip install promptledger-client`)
- [ ] Story 1.7 — Span ingestion API (`POST /v1/spans`, `GET /v1/traces/{id}/summary`)

### Epic 2 — Namespacing (deferred)
- [ ] Project namespacing and multi-tenant API keys

### Longer term
- [ ] OpenTelemetry export integration
- [ ] RBAC and team-based access control
- [ ] Evaluation and A/B testing framework
- [ ] Web dashboard and real-time analytics
- [ ] Trace comparison and anomaly detection
