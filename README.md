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
- **Workflow Execution Tracking**: OpenTelemetry-style spans for tracing multi-step agentic workflows
- **Prompt Registry**: Content-based versioning with deduplication
- **Multi-provider Execution**: OpenAI support with extensible adapter interface
- **Async-first Design**: Redis + Celery for production workloads
- **Full Lineage**: Complete execution tracking and parent-child relationships in Postgres
- **Deterministic Reproducibility**: Prompt → Version → Execution → Span traceability
- **Git Integration**: Automatic version detection for code-based prompts
- **Unified API**: Same interface regardless of prompt management approach
- **External Call Logging**: Track LLM calls made outside PromptLedger for complete visibility

## Architecture

```
Client (Agentic Workflow)
  │
  ▼
Prompt Registry & Execution API (FastAPI)
  │           │
  │           ├── Registry ops → Postgres (prompts, versions)
  │           │
  │           ├── Span tracking → Postgres (traces, parent-child)
  │           │
  │           └── Submit execution → Redis (Celery)
  │
  ▼
Worker Pool (Celery)
  │
  └── Provider Adapter (OpenAI)
           │
           ▼
        OpenAI API
           │
           ▼
  Results + Telemetry → Postgres (executions, spans)
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

## Workflow Execution Tracking

PromptLedger provides OpenTelemetry-style workflow tracking to trace and correlate executions across multi-step agentic workflows. This enables debugging, cost attribution, and compliance auditing for complex LLM applications.

### Core Concepts

- **Trace**: A collection of spans representing a single workflow execution from start to finish
- **Span**: A single operation within a trace (prompt execution, tool call, retrieval, guardrail check)
- **trace_id**: Groups all spans in one workflow run
- **parent_span_id**: Creates parent-child relationships for nested operations

### Tracking a Multi-Step Workflow

```python
from prompt_ledger import PromptLedger
import uuid

ledger = PromptLedger()

# Generate a trace_id for this workflow run
trace_id = str(uuid.uuid4())

# Step 1: RAG Retrieval (create root span)
retrieval_result = ledger.execute(
    "document_retrieval",
    variables={"query": "What is our PTO policy?"},
    trace_id=trace_id,
    span_name="rag_retrieval",
    span_kind="retrieval"
)
retrieval_span_id = retrieval_result["span_id"]

# Step 2: Response Generation (child of retrieval)
generation_result = ledger.execute(
    "policy_response",
    variables={
        "query": "What is our PTO policy?",
        "context": retrieval_result["output"]
    },
    trace_id=trace_id,
    parent_span_id=retrieval_span_id,
    span_name="response_generation",
    span_kind="llm"
)
generation_span_id = generation_result["span_id"]

# Step 3: Grounding Guardrail (child of generation)
guardrail_result = ledger.execute(
    "grounding_check",
    variables={
        "response": generation_result["output"],
        "source_docs": retrieval_result["output"]
    },
    trace_id=trace_id,
    parent_span_id=generation_span_id,
    span_name="grounding_guardrail",
    span_kind="guardrail"
)

# Get complete workflow trace
trace = ledger.get_trace(trace_id)
print(f"Total workflow duration: {trace['duration_ms']}ms")
print(f"Total tokens used: {trace['total_tokens']}")
print(f"Total cost: ${trace['total_cost']}")

# Get execution tree
tree = ledger.get_trace_tree(trace_id)
for span in tree:
    indent = "  " * span["depth"]
    print(f"{indent}{span['name']}: {span['duration_ms']}ms")
```

### Logging External LLM Calls

Track LLM calls made directly to providers (outside PromptLedger) for complete workflow visibility:

```python
# Your application makes a direct OpenAI call
import openai
response = openai.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Analyze this data..."}]
)

# Log it to PromptLedger for tracking
ledger.log_external_span(
    trace_id=trace_id,
    parent_span_id=parent_span_id,
    name="direct_openai_analysis",
    kind="llm",
    input_data={"messages": [...]},
    output_data={"response": response.choices[0].message.content},
    model="gpt-4",
    prompt_tokens=response.usage.prompt_tokens,
    completion_tokens=response.usage.completion_tokens,
    duration_ms=450
)
```

### Workflow Analytics

```bash
# Get trace summary
curl -X GET "http://localhost:8000/v1/traces/{trace_id}/summary" \
  -H "X-API-Key: dev-key-change-in-production"

# Get trace tree
curl -X GET "http://localhost:8000/v1/traces/{trace_id}/tree" \
  -H "X-API-Key: dev-key-change-in-production"

# Get all spans in a trace
curl -X GET "http://localhost:8000/v1/traces/{trace_id}/spans" \
  -H "X-API-Key: dev-key-change-in-production"
```

### Use Cases

**Debugging Failed Workflows**
- Identify which step in a multi-step workflow caused a failure
- See exact inputs and outputs at each step
- Compare successful vs failed workflow runs

**Cost Attribution**
- Aggregate token costs across all steps in a workflow
- Identify expensive operations for optimization
- Track costs by workflow type or user

**Compliance & Auditing**
- Complete audit trail of all operations in a workflow
- Prove that guardrails were executed before responses
- Reconstruct decision chains for regulatory requirements

**Performance Optimization**
- Identify bottleneck steps in workflows
- Measure end-to-end latency across workflow runs
- Optimize parallel vs sequential execution patterns

## Dual-Mode Usage Patterns

Prompt Ledger supports two distinct approaches to prompt management:

### Mode 1: Full Management (Database-First)

**Best for**: Marketing teams, dynamic content, non-technical users

```python
from prompt_ledger import PromptLedger

# Initialize in full management mode
ledger = PromptLedger(mode="full")

# Create and manage prompts via API
ledger.create_prompt(
    name="welcome_email",
    template="Hello {{name}}, welcome to {{company}}!",
    description="Welcome message for new users"
)

# Execute prompts
result = ledger.execute("welcome_email", {
    "name": "Sarah",
    "company": "Acme Corp"
})

# Update prompts dynamically
ledger.update_prompt("welcome_email",
    "🎉 Hello {{name}}, welcome to {{company}}! We're excited to have you!")
```

### Mode 2: Code-Based Tracking (Git-First)

**Best for**: Developer teams, version control, stable prompts

```python
# my_app/prompts.py
class Prompts:
    WELCOME = "Hello {{name}}, welcome to {{app}}!"
    ORDER_CONFIRMATION = "Order {{order_id}} is confirmed!"
    ERROR_MESSAGE = "Error: {{error}} - Please contact support."

    @classmethod
    def get_template(cls, name):
        return getattr(cls, name)

# my_app/main.py
from prompt_ledger import PromptLedger
from my_app.prompts import Prompts

# Initialize in tracking mode
ledger = PromptLedger(
    mode="tracking_only",
    code_registry=Prompts.get_template
)

# Register code prompts (detects changes automatically)
response = ledger.register_code_prompts([
    "WELCOME",
    "ORDER_CONFIRMATION",
    "ERROR_MESSAGE"
])

print(f"Registered {len(response['registered'])} prompts")
for prompt in response['registered']:
    print(f"  {prompt['name']}: v{prompt['version']} ({prompt['mode']})")

# Execute with automatic tracking
result = ledger.execute("WELCOME", {
    "name": "John",
    "app": "MyApp"
})

# Get unified analytics (works for both modes)
analytics = ledger.get_analytics(mode="all")
print(f"Total executions: {analytics['summary']['total_executions']}")
print(f"Full mode: {analytics['by_mode']['full']['execution_count']}")
print(f"Tracking mode: {analytics['by_mode']['tracking']['execution_count']}")

# Get prompt history (works for both modes)
history = ledger.get_prompt_history("WELCOME", mode="tracking")
print(f"Current version: {history['current_version']}")
for version in history['versions']:
    print(f"v{version['version']}: {version['execution_count']} executions")
```

### Choosing the Right Mode

| Factor | Full Management | Code-Based Tracking |
|--------|----------------|-------------------|
| **Team** | Mixed technical/non-technical | Developer-focused |
| **Update Frequency** | High, dynamic changes | Low, stable templates |
| **Version Control** | Database-managed | Git-based |
| **Testing** | Runtime testing | Unit test friendly |
| **Deployment** | No code changes needed | Code deployment required |
| **Analytics** | Full prompt lifecycle | Usage tracking only |

### Migration Between Modes

```python
# Start with tracking, migrate to full management
ledger = PromptLedger(mode="tracking_only")
# ... develop prompts in code ...

# When ready for dynamic management:
ledger.migrate_to_full_mode([
    ("WELCOME", Prompts.WELCOME),
    ("ORDER_CONFIRMATION", Prompts.ORDER_CONFIRMATION)
])
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

### Recently Completed ✅
- [x] Dual-mode prompt management (full vs tracking)
- [x] Workflow execution tracking with OpenTelemetry-style spans
- [x] Parent-child relationship tracking for nested operations
- [x] External LLM call logging
- [x] Unified analytics across modes and workflows

### Planned Features
- [ ] Multi-provider support (Anthropic, Google, Cohere, etc.)
- [ ] OpenTelemetry export integration
- [ ] RBAC and team-based access control
- [ ] Evaluation and A/B testing framework
- [ ] Advanced cost tracking and budgeting dashboards
- [ ] Prompt optimization suggestions based on execution data
- [ ] Web dashboard and real-time analytics
- [ ] Multi-tenancy support
- [ ] Trace comparison and anomaly detection
- [ ] Workflow templates and best practices library
