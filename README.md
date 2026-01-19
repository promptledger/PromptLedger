# Prompt Ledger

A centralized, governed control plane for GenAI prompts with registry, execution, and lineage tracking.

## Features

- **Prompt Registry**: Content-based versioning with deduplication
- **Multi-provider Execution**: OpenAI support with extensible adapter interface
- **Async-first Design**: Redis + Celery for production workloads
- **Full Lineage**: Complete execution tracking in Postgres
- **Deterministic Reproducibility**: Prompt → Version → Execution traceability

## Architecture

```
Client
  │
  ▼
Prompt Registry & Execution API (FastAPI)
  │           │
  │           ├── Registry ops → Postgres
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

The service uses the following main tables:

- `prompts` - Prompt definitions and metadata
- `prompt_versions` - Versioned prompt templates with checksums
- `models` - AI model configurations
- `executions` - Execution tracking and results
- `execution_inputs` - Input variables for each execution

See the [design specification](prompt_registry_execution_service_final_design_spec.md) for complete schema details.

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

- [ ] Multi-provider support (Anthropic, Google, etc.)
- [ ] RBAC and team-based access control
- [ ] Evaluation and A/B testing framework
- [ ] Cost tracking and budgeting
- [ ] Prompt optimization suggestions
- [ ] Web dashboard and analytics
- [ ] Multi-tenancy support
