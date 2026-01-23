# Railway Integration Guide for PromptLedger

This guide explains how to integrate PromptLedger into an existing Railway application with Python, PostgreSQL, API, and Frontend services.

## Overview

PromptLedger is a centralized prompt management and execution service that provides:
- Prompt registry with versioning
- LLM execution tracking and lineage
- Dual-mode management (database-first or code-based)
- Async execution with Redis/Celery
- OpenAI integration with extensible provider support

## Architecture Integration

```
Your Existing Railway App:
├── Python App Service
├── PostgreSQL Service
├── API Service
└── Frontend Service

Adding PromptLedger:
├── PromptLedger API Service (FastAPI)
├── PromptLedger Worker Service (Celery)
├── Redis Service (addition)
└── Additional Tables in PostgreSQL
```

## Step-by-Step Integration

### 1. Add Redis Service

First, add a Redis service to your Railway project for PromptLedger's async execution:

```bash
# Using Railway CLI
railway add redis
```

Or add via Railway dashboard:
1. Go to your project
2. Click "New Service"
3. Select "Redis"
4. Name it `prompt-ledger-redis`

### 2. Extend PostgreSQL Database

PromptLedger needs additional tables in your existing PostgreSQL database.

#### 2.1 Add Dependencies

Add PromptLedger to your Python app's requirements:

```txt
# requirements.txt
prompt-ledger>=0.1.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
psycopg[binary]>=3.1.0
asyncpg>=0.29.0
sqlalchemy[asyncio]>=2.0.0
alembic>=1.12.0
redis>=5.0.0
celery>=5.3.0
pydantic>=2.4.0
jinja2>=3.1.0
openai>=1.3.0
```

#### 2.2 Database Migration

Create a migration to add PromptLedger tables:

```python
# alembic/versions/add_prompt_ledger_tables.py

"""Add PromptLedger tables

Revision ID: add_prompt_ledger
Revises: <your_previous_revision>
Create Date: <current_date>

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_prompt_ledger'
down_revision = '<your_previous_revision>'
branch_labels = None
depends_on = None

def upgrade():
    # Prompts table
    op.create_table('prompts',
        sa.Column('prompt_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('mode', sa.Enum('full', 'tracking', name='promptmode'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_team', sa.String(length=100), nullable=True),
        sa.Column('active_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('prompt_id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_prompts_name'), 'prompts', ['name'], unique=False)

    # Prompt versions table
    op.create_table('prompt_versions',
        sa.Column('version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prompt_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('template_source', sa.Text(), nullable=False),
        sa.Column('checksum_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.Enum('active', 'draft', 'archived', name='versionstatus'), nullable=False),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompts.prompt_id'], ),
        sa.PrimaryKeyConstraint('version_id'),
        sa.UniqueConstraint('prompt_id', 'checksum_hash')
    )
    op.create_index(op.f('ix_prompt_versions_prompt_id'), 'prompt_versions', ['prompt_id'], unique=False)

    # Models table
    op.create_table('models',
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('supports_streaming', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('model_id'),
        sa.UniqueConstraint('provider', 'model_name')
    )

    # Executions table
    op.create_table('executions',
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prompt_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_mode', sa.Enum('sync', 'async', name='executionmode'), nullable=False),
        sa.Column('status', sa.Enum('queued', 'running', 'succeeded', 'failed', name='executionstatus'), nullable=False),
        sa.Column('rendered_prompt', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('response_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('correlation_id', sa.String(length=100), nullable=True),
        sa.Column('idempotency_key', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['model_id'], ['models.model_id'], ),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompts.prompt_id'], ),
        sa.ForeignKeyConstraint(['version_id'], ['prompt_versions.version_id'], ),
        sa.PrimaryKeyConstraint('execution_id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index(op.f('ix_executions_prompt_id'), 'executions', ['prompt_id'], unique=False)
    op.create_index(op.f('ix_executions_status'), 'executions', ['status'], unique=False)

    # Execution inputs table
    op.create_table('execution_inputs',
        sa.Column('input_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('variables_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('model_config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('params_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.execution_id'], ),
        sa.PrimaryKeyConstraint('input_id')
    )

    # Spans table for workflow tracking
    op.create_table('spans',
        sa.Column('span_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trace_id', sa.String(length=100), nullable=False),
        sa.Column('parent_span_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('input_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.execution_id'], ),
        sa.ForeignKeyConstraint(['parent_span_id'], ['spans.span_id'], ),
        sa.PrimaryKeyConstraint('span_id')
    )
    op.create_index(op.f('ix_spans_trace_id'), 'spans', ['trace_id'], unique=False)
    op.create_index(op.f('ix_spans_execution_id'), 'spans', ['execution_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_spans_execution_id'), table_name='spans')
    op.drop_index(op.f('ix_spans_trace_id'), table_name='spans')
    op.drop_table('spans')
    op.drop_table('execution_inputs')
    op.drop_index(op.f('ix_executions_status'), table_name='executions')
    op.drop_index(op.f('ix_executions_prompt_id'), table_name='executions')
    op.drop_table('executions')
    op.drop_table('models')
    op.drop_index(op.f('ix_prompt_versions_prompt_id'), table_name='prompt_versions')
    op.drop_table('prompt_versions')
    op.drop_index(op.f('ix_prompts_name'), table_name='prompts')
    op.drop_table('prompts')
    op.execute('DROP TYPE IF EXISTS promptmode')
    op.execute('DROP TYPE IF EXISTS versionstatus')
    op.execute('DROP TYPE IF EXISTS executionmode')
    op.execute('DROP TYPE IF EXISTS executionstatus')
```

Run the migration:

```bash
alembic upgrade head
```

### 3. Create PromptLedger API Service

Create a new service in your Railway project for the PromptLedger API.

#### 3.1 Dockerfile for PromptLedger API

```dockerfile
# prompt-ledger-api/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "prompt_ledger.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 3.2 Railway Service Configuration

Create `railway.toml` for the PromptLedger API service:

```toml
# prompt-ledger-api/railway.toml
[build]
builder = "nixpacks"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 100
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 10

[[services]]
name = "prompt-ledger-api"

[services.variables]
PORT = "8000"
DATABASE_URL = "${{Postgres.DATABASE_URL}}"
REDIS_URL = "${{Redis.REDIS_URL}}"
OPENAI_API_KEY = "${{OPENAI_API_KEY}}"
API_KEY = "${{PROMPT_LEDGER_API_KEY}}"
```

### 4. Create PromptLedger Worker Service

Create a separate service for Celery workers.

#### 4.1 Dockerfile for Worker

```dockerfile
# prompt-ledger-worker/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

CMD ["celery", "-A", "prompt_ledger.workers.celery_app", "worker", "--pool=solo", "--loglevel=info"]
```

#### 4.2 Worker Service Configuration

```toml
# prompt-ledger-worker/railway.toml
[build]
builder = "nixpacks"

[deploy]
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 10

[[services]]
name = "prompt-ledger-worker"

[services.variables]
DATABASE_URL = "${{Postgres.DATABASE_URL}}"
REDIS_URL = "${{Redis.REDIS_URL}}"
OPENAI_API_KEY = "${{OPENAI_API_KEY}}"
API_KEY = "${{PROMPT_LEDGER_API_KEY}}"
```

### 5. Update Your Application

#### 5.1 Install PromptLedger SDK

```bash
pip install prompt-ledger
```

#### 5.2 Initialize PromptLedger in Your App

```python
# your_app/main.py
from prompt_ledger import PromptLedger
import os

# Initialize PromptLedger client
ledger = PromptLedger(
    api_url=os.getenv("PROMPT_LEDGER_URL", "https://prompt-ledger-api.yourapp.railway.app"),
    api_key=os.getenv("PROMPT_LEDGER_API_KEY")
)

# Example: Create a prompt
def setup_prompts():
    ledger.create_prompt(
        name="user_welcome",
        template="Hello {{name}}! Welcome to {{app_name}}.",
        description="Welcome message for new users",
        owner_team="product"
    )

# Example: Execute a prompt
def send_welcome_email(user_name, app_name):
    result = ledger.execute(
        prompt_name="user_welcome",
        variables={
            "name": user_name,
            "app_name": app_name
        },
        model={
            "provider": "openai",
            "model_name": "gpt-4o-mini"
        },
        params={
            "temperature": 0.7,
            "max_tokens": 100
        }
    )
    return result["response_text"]
```

#### 5.3 Environment Variables

Add these to your existing services:

```bash
# In your Railway environment variables
PROMPT_LEDGER_URL=https://prompt-ledger-api.yourapp.railway.app
PROMPT_LEDGER_API_KEY=your-secure-api-key
OPENAI_API_KEY=your-openai-api-key
```

### 6. Frontend Integration

Add PromptLedger integration to your frontend:

```javascript
// frontend/src/services/promptLedger.js
const API_BASE = process.env.REACT_APP_PROMPT_LEDGER_URL || 'https://prompt-ledger-api.yourapp.railway.app';

class PromptLedgerService {
  constructor(apiKey) {
    this.apiKey = apiKey;
  }

  async executePrompt(promptName, variables, model = { provider: 'openai', model_name: 'gpt-4o-mini' }) {
    const response = await fetch(`${API_BASE}/v1/executions:run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this.apiKey,
      },
      body: JSON.stringify({
        prompt_name: promptName,
        environment: 'production',
        variables,
        model,
        params: {
          temperature: 0.7,
          max_tokens: 500,
        },
      }),
    });

    if (!response.ok) {
      throw new Error(`PromptLedger error: ${response.statusText}`);
    }

    return response.json();
  }

  async getPromptAnalytics(promptName) {
    const response = await fetch(`${API_BASE}/v1/analytics/prompts/${promptName}`, {
      headers: {
        'X-API-Key': this.apiKey,
      },
    });

    return response.json();
  }
}

export default PromptLedgerService;
```

### 7. Railway Project Structure

Your Railway project will now look like:

```
your-project/
├── existing-python-app/          # Your current app
├── existing-api/                 # Your current API
├── existing-frontend/            # Your current frontend
├── existing-postgres/            # Your current database
├── prompt-ledger-redis/          # New Redis service
├── prompt-ledger-api/            # New PromptLedger API
└── prompt-ledger-worker/         # New PromptLedger worker
```

## Usage Patterns

### Pattern 1: Full Management Mode

For dynamic prompts managed via API:

```python
# Marketing team updates email templates
ledger.update_prompt("newsletter_header",
    "🎉 {{month}} {{year}} Newsletter - {{theme}}!")

# Execute with latest version
result = ledger.execute("newsletter_header", {
    "month": "January",
    "year": "2026",
    "theme": "New Features"
})
```

### Pattern 2: Code-Based Tracking Mode

For stable prompts in your codebase:

```python
# your_app/prompts.py
class Prompts:
    USER_SUMMARY = "Summarize user {{user_id}} activity in the last {{days}} days."
    ERROR_MESSAGE = "Error: {{error}} occurred in {{context}}."

# Register prompts on startup
ledger.register_code_prompts([
    ("USER_SUMMARY", Prompts.USER_SUMMARY),
    ("ERROR_MESSAGE", Prompts.ERROR_MESSAGE)
])

# Execute with tracking
result = ledger.execute("USER_SUMMARY", {
    "user_id": "12345",
    "days": "30"
})
```

## Monitoring & Observability

### Health Checks

- PromptLedger API: `GET /health`
- Check service logs in Railway dashboard

### Analytics

Access execution analytics via API:

```bash
curl -X GET "https://prompt-ledger-api.yourapp.railway.app/v1/analytics/summary" \
  -H "X-API-Key: your-api-key"
```

### Logging

All services log to Railway's built-in logging. Key logs to monitor:
- Prompt execution failures
- Worker queue depth
- Database connection issues

## Security Considerations

1. **API Keys**: Use strong, randomly generated API keys
2. **Environment Variables**: Never commit secrets to git
3. **Database Security**: PromptLedger tables contain sensitive data
4. **Network Security**: All services communicate within Railway's private network

## Scaling Considerations

### Horizontal Scaling

- **API Service**: Railway auto-scales based on traffic
- **Worker Service**: Add more worker instances for high throughput
- **Redis**: Railway's managed Redis handles scaling automatically
- **Database**: Consider read replicas for analytics queries

### Performance Optimization

1. **Connection Pooling**: Configure database connection pools
2. **Caching**: Redis caches active prompt versions
3. **Queue Management**: Separate queues for different priority tasks

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Verify DATABASE_URL format
   - Check database service health
   - Ensure migrations are applied

2. **Redis Connection Errors**
   - Verify REDIS_URL format
   - Check Redis service health
   - Confirm network connectivity

3. **Worker Not Processing Tasks**
   - Check worker service logs
   - Verify Celery configuration
   - Monitor queue depth

4. **API Authentication Failures**
   - Verify API_KEY environment variable
   - Check header format: `X-API-Key`
   - Ensure key matches between services

### Debug Commands

```bash
# Check service status
railway status

# View service logs
railway logs prompt-ledger-api
railway logs prompt-ledger-worker

# Access service shell (for debugging)
railway shell prompt-ledger-api

# Test database connection
railway run prompt-ledger-api -- python -c "from prompt_ledger.db import engine; print(engine.url)"
```

## Migration Strategy

### Phase 1: Setup (1-2 days)
- Add Redis service
- Run database migrations
- Deploy PromptLedger services

### Phase 2: Integration (2-3 days)
- Install SDK in existing app
- Implement basic prompt usage
- Test end-to-end functionality

### Phase 3: Migration (1-2 weeks)
- Move existing prompts to PromptLedger
- Update frontend integration
- Monitor performance and usage

### Phase 4: Optimization (ongoing)
- Fine-tune worker scaling
- Implement analytics dashboards
- Optimize prompt performance

## Cost Considerations

### Railway Service Costs
- Additional API service: ~$5-20/month
- Worker service: ~$5-20/month
- Redis service: ~$5-15/month

### OpenAI API Costs
- Charged per token usage
- Monitor via PromptLedger analytics
- Set usage limits and alerts

## Support

- **Documentation**: [PromptLedger README](./README.md)
- **Architecture**: [Architecture Guide](./ARCHITECTURE.md)
- **Issues**: Create GitHub issue for bugs
- **Community**: Join discussions for usage questions

---

*This integration guide assumes you're familiar with Railway's platform and have an existing Python application with PostgreSQL database.*
