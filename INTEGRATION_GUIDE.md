# PromptLedger Integration Guide

**For Application Development Teams**

This guide provides step-by-step instructions for integrating PromptLedger into your AI-powered applications. Whether you're building chatbots, RAG systems, or multi-agent workflows, PromptLedger gives you centralized prompt management, execution tracking, and full observability.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start Integration](#quick-start-integration)
4. [Integration Patterns](#integration-patterns)
5. [Workflow Tracking for Agentic Applications](#workflow-tracking-for-agentic-applications)
6. [Connecting to Railway-Hosted PromptLedger](#connecting-to-railway-hosted-promptledger)
7. [Production Deployment](#production-deployment)
8. [Security Best Practices](#security-best-practices)
9. [Monitoring & Observability](#monitoring--observability)
10. [Troubleshooting](#troubleshooting)
11. [API Reference Quick Guide](#api-reference-quick-guide)

---

## Overview

### What is PromptLedger?

PromptLedger is an open-source prompt registry and execution framework that solves **prompt sprawl** in GenAI applications. It provides:

- **Centralized Prompt Management**: Store, version, and govern all prompts in one place
- **Execution Tracking**: Full lineage of every LLM call with telemetry
- **Workflow Observability**: OpenTelemetry-style tracing for multi-step agentic workflows
- **Dual-Mode Flexibility**: Database-managed prompts OR code-based tracking

### Why Integrate PromptLedger?

| Challenge | PromptLedger Solution |
|-----------|----------------------|
| Prompts scattered across code, configs, notebooks | Centralized registry with versioning |
| No visibility into prompt changes | Content-based versioning with full history |
| Debugging multi-step AI workflows | Parent-child span tracking |
| Cost attribution across teams | Execution telemetry with token/cost tracking |
| Compliance and audit requirements | Complete execution lineage |

---

## Prerequisites

### System Requirements

- **Python**: 3.11+
- **PostgreSQL**: 15+
- **Redis**: 7+
- **Network**: HTTPS access to PromptLedger API endpoint

### Required Credentials

| Credential | Description | Where to Obtain |
|------------|-------------|-----------------|
| `PROMPTLEDGER_API_KEY` | API authentication key | Your PromptLedger administrator |
| `PROMPTLEDGER_API_URL` | Base URL of PromptLedger service | See deployment options below |
| `OPENAI_API_KEY` | OpenAI API key (if using OpenAI provider) | [OpenAI Platform](https://platform.openai.com) |

### Deployment Options

| Deployment | API URL Format | Notes |
|------------|----------------|-------|
| **Local Development** | `http://localhost:8000` | Docker Compose setup |
| **Railway (Cloud)** | `https://promptledger-api-production-XXXX.up.railway.app` | Managed cloud hosting |
| **Self-Hosted** | `https://promptledger.yourcompany.com` | Your infrastructure |

---

## Quick Start Integration

### Step 1: Install Dependencies

```bash
pip install httpx python-dotenv
```

### Step 2: Configure Environment

Create a `.env` file in your application root:

```env
# PromptLedger Configuration
PROMPTLEDGER_API_URL=http://localhost:8000
PROMPTLEDGER_API_KEY=your-api-key-here

# LLM Provider (required for execution)
OPENAI_API_KEY=your-openai-key-here
```

### Step 3: Create Your First Prompt

```python
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("PROMPTLEDGER_API_URL")
API_KEY = os.getenv("PROMPTLEDGER_API_KEY")

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Create/update a prompt
response = httpx.put(
    f"{API_URL}/v1/prompts/customer_support",
    headers=headers,
    json={
        "description": "Customer support response generator",
        "owner_team": "Support-AI",
        "template_source": """You are a helpful customer support agent.

Customer Query: {{query}}
Customer Sentiment: {{sentiment}}

Provide a professional, empathetic response that addresses their concern.""",
        "created_by": "integration-guide",
        "set_active": True
    }
)

print(f"Prompt created: {response.json()}")
```

### Step 4: Execute the Prompt

```python
# Synchronous execution
response = httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={
        "prompt_name": "customer_support",
        "environment": "dev",
        "variables": {
            "query": "My order hasn't arrived yet",
            "sentiment": "frustrated"
        },
        "model": {
            "provider": "openai",
            "model_name": "gpt-4o-mini"
        },
        "params": {
            "max_new_tokens": 500,
            "temperature": 0.7
        }
    }
)

result = response.json()
print(f"Response: {result['response_text']}")
print(f"Tokens used: {result['telemetry']['prompt_tokens']} + {result['telemetry']['response_tokens']}")
```

---

## Integration Patterns

PromptLedger supports two distinct integration modes. Choose based on your team's workflow.

### Mode 1: Full Management (Database-First)

**Best for**: Marketing teams, dynamic content, non-technical users, A/B testing

Prompts are stored and managed entirely in PromptLedger's database. Changes don't require code deployments.

```python
# Create prompt via API
httpx.put(
    f"{API_URL}/v1/prompts/welcome_email",
    headers=headers,
    json={
        "template_source": "Hello {{name}}, welcome to {{company}}!",
        "description": "Welcome email template",
        "owner_team": "Marketing",
        "set_active": True
    }
)

# Execute prompt
httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={
        "prompt_name": "welcome_email",
        "variables": {"name": "Sarah", "company": "Acme Corp"},
        "model": {"provider": "openai", "model_name": "gpt-4o-mini"}
    }
)

# Update prompt without code deployment
httpx.put(
    f"{API_URL}/v1/prompts/welcome_email",
    headers=headers,
    json={
        "template_source": "🎉 Hello {{name}}, welcome aboard at {{company}}!",
        "set_active": True
    }
)
```

### Mode 2: Code-Based Tracking (Git-First)

**Best for**: Engineering teams, version control, CI/CD integration, unit-testable prompts

Prompts are defined in your application code and tracked by PromptLedger for analytics and versioning.

```python
# prompts.py - Define prompts in code
class Prompts:
    WELCOME = "Hello {{name}}, welcome to {{app}}!"
    ORDER_CONFIRMATION = "Order {{order_id}} is confirmed!"
    ERROR_MESSAGE = "Error: {{error}} - Please contact support."

    @classmethod
    def get_template(cls, name: str) -> str:
        return getattr(cls, name)
```

```python
# main.py - Register and execute code prompts
import hashlib

# Register code prompts with PromptLedger
def register_code_prompts():
    prompts_to_register = []
    for name in ["WELCOME", "ORDER_CONFIRMATION", "ERROR_MESSAGE"]:
        template = Prompts.get_template(name)
        template_hash = hashlib.sha256(template.encode()).hexdigest()
        prompts_to_register.append({
            "name": name,
            "template_source": template,
            "template_hash": template_hash
        })

    response = httpx.post(
        f"{API_URL}/v1/prompts/register-code",
        headers=headers,
        json={"prompts": prompts_to_register}
    )
    return response.json()

# Call on application startup
registration_result = register_code_prompts()
print(f"Registered {len(registration_result['registered'])} prompts")

# Execute with tracking
response = httpx.post(
    f"{API_URL}/v1/prompts/WELCOME/execute",
    headers=headers,
    json={
        "variables": {"name": "John", "app": "MyApp"},
        "model_name": "gpt-4o-mini",
        "mode": "sync"
    }
)
```

### Choosing the Right Mode

| Factor | Full Management | Code-Based Tracking |
|--------|----------------|---------------------|
| **Team** | Mixed technical/non-technical | Developer-focused |
| **Update Frequency** | High, dynamic changes | Low, stable templates |
| **Version Control** | Database-managed | Git-based |
| **Testing** | Runtime testing | Unit test friendly |
| **Deployment** | No code changes needed | Code deployment required |
| **Analytics** | Full prompt lifecycle | Usage tracking only |

---

## Workflow Tracking for Agentic Applications

PromptLedger provides OpenTelemetry-style tracing to correlate executions across multi-step workflows—essential for debugging, cost attribution, and compliance in agentic AI systems.

### Core Concepts

| Concept | Description |
|---------|-------------|
| **Trace** | Collection of spans representing one workflow run |
| **Span** | Single operation (LLM call, tool use, retrieval) |
| **trace_id** | Groups all spans in one workflow |
| **parent_span_id** | Creates parent-child relationships |

### Example: RAG Pipeline with Guardrails

```python
import uuid
import httpx

trace_id = str(uuid.uuid4())

# Step 1: Document Retrieval
retrieval_response = httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={
        "prompt_name": "document_retrieval",
        "variables": {"query": "What is our PTO policy?"},
        "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
        "trace_id": trace_id,
        "span_name": "rag_retrieval",
        "span_kind": "retrieval"
    }
)
retrieval_span_id = retrieval_response.json()["span_id"]

# Step 2: Response Generation (child of retrieval)
generation_response = httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={
        "prompt_name": "policy_response",
        "variables": {
            "query": "What is our PTO policy?",
            "context": retrieval_response.json()["response_text"]
        },
        "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
        "trace_id": trace_id,
        "parent_span_id": retrieval_span_id,
        "span_name": "response_generation",
        "span_kind": "llm"
    }
)
generation_span_id = generation_response.json()["span_id"]

# Step 3: Grounding Guardrail (child of generation)
guardrail_response = httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={
        "prompt_name": "grounding_check",
        "variables": {
            "response": generation_response.json()["response_text"],
            "source_docs": retrieval_response.json()["response_text"]
        },
        "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
        "trace_id": trace_id,
        "parent_span_id": generation_span_id,
        "span_name": "grounding_guardrail",
        "span_kind": "guardrail"
    }
)

# Get complete workflow trace
trace_summary = httpx.get(
    f"{API_URL}/v1/traces/{trace_id}/summary",
    headers=headers
)
print(f"Total duration: {trace_summary.json()['duration_ms']}ms")
print(f"Total tokens: {trace_summary.json()['total_tokens']}")
print(f"Total cost: ${trace_summary.json()['total_cost']}")
```

### Logging External LLM Calls

Track LLM calls made directly to providers (outside PromptLedger) for complete visibility:

```python
import openai
import time

# Your application makes a direct OpenAI call
start_time = time.time()
openai_response = openai.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Analyze this data..."}]
)
duration_ms = int((time.time() - start_time) * 1000)

# Log it to PromptLedger for tracking
httpx.post(
    f"{API_URL}/v1/spans",
    headers=headers,
    json={
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "name": "direct_openai_analysis",
        "kind": "llm",
        "input_data": {"messages": [{"role": "user", "content": "Analyze..."}]},
        "output_data": {"response": openai_response.choices[0].message.content},
        "model": "gpt-4",
        "prompt_tokens": openai_response.usage.prompt_tokens,
        "completion_tokens": openai_response.usage.completion_tokens,
        "duration_ms": duration_ms
    }
)
```

### Workflow Analytics Endpoints

```bash
# Get trace summary
GET /v1/traces/{trace_id}/summary

# Get trace tree (parent-child hierarchy)
GET /v1/traces/{trace_id}/tree

# Get all spans in a trace
GET /v1/traces/{trace_id}/spans
```

---

## Connecting to Railway-Hosted PromptLedger

If your organization deploys PromptLedger on [Railway](https://railway.app), follow these steps to connect your application.

> 📖 **For deploying PromptLedger itself to Railway**, see [RAILWAY_INTEGRATION.md](RAILWAY_INTEGRATION.md).

### Railway Environment Setup

```env
# .env for Railway-hosted PromptLedger
PROMPTLEDGER_API_URL=https://promptledger-api-production-XXXX.up.railway.app
PROMPTLEDGER_API_KEY=your-railway-api-key-here
OPENAI_API_KEY=your-openai-key-here
```

> **Note**: Get your exact Railway URL from your Railway dashboard under your PromptLedger API service → Settings → Domains.

### Connecting from Your Application

```python
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Railway-hosted PromptLedger configuration
API_URL = os.getenv("PROMPTLEDGER_API_URL")  # e.g., https://promptledger-api-production-XXXX.up.railway.app
API_KEY = os.getenv("PROMPTLEDGER_API_KEY")

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Test connection
def test_connection():
    response = httpx.get(f"{API_URL}/health", timeout=10.0)
    if response.status_code == 200:
        print("✅ Connected to Railway-hosted PromptLedger")
        return True
    else:
        print(f"❌ Connection failed: {response.status_code}")
        return False

# Execute prompt via Railway
def execute_prompt(prompt_name: str, variables: dict):
    response = httpx.post(
        f"{API_URL}/v1/executions:run",
        headers=headers,
        json={
            "prompt_name": prompt_name,
            "environment": "production",
            "variables": variables,
            "model": {"provider": "openai", "model_name": "gpt-4o-mini"}
        },
        timeout=60.0
    )
    return response.json()
```

### Railway-Specific Considerations

| Consideration | Recommendation |
|---------------|----------------|
| **Timeouts** | Railway has 100s request timeout; use async for long operations |
| **Private Networking** | Use Railway's private network for service-to-service calls |
| **Environment Variables** | Store secrets in Railway's encrypted environment variables |
| **Scaling** | Railway auto-scales; monitor worker queue depth for async jobs |

### Connecting from Another Railway Service

If your application is also on Railway, use private networking for faster, more secure connections:

```python
import os

# Use Railway's internal networking (within same project)
# Format: http://<service-name>.railway.internal:<port>
API_URL = os.getenv(
    "PROMPTLEDGER_API_URL",
    "http://promptledger-api.railway.internal:8000"  # Internal URL
)
```

### Frontend Integration (React/Next.js on Railway)

```javascript
// services/promptLedger.js
const API_URL = process.env.NEXT_PUBLIC_PROMPTLEDGER_URL
  || 'https://promptledger-api-production-XXXX.up.railway.app';

export async function executePrompt(promptName, variables) {
  const response = await fetch(`${API_URL}/v1/executions:run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.PROMPTLEDGER_API_KEY,
    },
    body: JSON.stringify({
      prompt_name: promptName,
      environment: 'production',
      variables,
      model: { provider: 'openai', model_name: 'gpt-4o-mini' }
    }),
  });

  if (!response.ok) {
    throw new Error(`PromptLedger error: ${response.status}`);
  }

  return response.json();
}
```

### Railway Deployment Checklist

Before going live with Railway-hosted PromptLedger:

- [ ] **API URL configured** — Verify `PROMPTLEDGER_API_URL` points to your Railway service
- [ ] **API key set** — Use a strong, randomly-generated key (not the dev default)
- [ ] **OpenAI key configured** — Set `OPENAI_API_KEY` in Railway environment
- [ ] **Health check passing** — `GET /health` returns 200
- [ ] **Worker service running** — Check Railway dashboard for worker status
- [ ] **Database migrations applied** — Run `alembic upgrade head` on deployment
- [ ] **Async execution tested** — Verify submit + poll workflow works

### Railway Pricing Impact

| Component | Estimated Monthly Cost |
|-----------|----------------------|
| PromptLedger API | $5–20 (usage-based) |
| Celery Worker | $5–20 (usage-based) |
| Redis | $5–15 |
| PostgreSQL (shared with your app) | Included |

---

## Production Deployment

### Asynchronous Execution (Recommended)

For production workloads, use async execution to avoid blocking your application:

```python
# Submit execution asynchronously
submit_response = httpx.post(
    f"{API_URL}/v1/executions:submit",
    headers=headers,
    json={
        "prompt_name": "document_summarizer",
        "variables": {"document": large_document_text},
        "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
        "params": {"max_new_tokens": 2000}
    }
)
execution_id = submit_response.json()["execution_id"]

# Poll for completion
import time

while True:
    status_response = httpx.get(
        f"{API_URL}/v1/executions/{execution_id}",
        headers=headers
    )
    status = status_response.json()

    if status["status"] in ["succeeded", "failed"]:
        break

    time.sleep(1)  # Poll every second

if status["status"] == "succeeded":
    print(f"Result: {status['response_text']}")
else:
    print(f"Error: {status['error_message']}")
```

### Idempotency

Prevent duplicate executions using idempotency keys:

```python
import uuid

idempotency_key = f"order-{order_id}-confirmation"

response = httpx.post(
    f"{API_URL}/v1/executions:submit",
    headers={
        **headers,
        "Idempotency-Key": idempotency_key
    },
    json={
        "prompt_name": "order_confirmation",
        "variables": {"order_id": order_id}
    }
)

# Same idempotency key returns the same execution (no duplicate)
```

### Correlation IDs

Link related executions across your system:

```python
correlation_id = f"user-session-{session_id}"

response = httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={
        "prompt_name": "chat_response",
        "variables": {"message": user_message},
        "correlation_id": correlation_id  # Links all executions for this session
    }
)
```

### Environment Configuration

Use environments to separate dev, staging, and production:

```python
# Development
response = httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={
        "prompt_name": "customer_support",
        "environment": "dev",  # or "staging", "production"
        "variables": {...}
    }
)
```

---

## Security Best Practices

### API Key Management

```python
import os

# ❌ Never hardcode API keys
API_KEY = "sk-abc123..."

# ✅ Use environment variables
API_KEY = os.getenv("PROMPTLEDGER_API_KEY")

# ✅ Use secrets management (AWS Secrets Manager, HashiCorp Vault, etc.)
from your_secrets_manager import get_secret
API_KEY = get_secret("promptledger/api-key")
```

### Key Rotation

Request multiple API keys and rotate periodically:

```python
# Support graceful key rotation
API_KEYS = [
    os.getenv("PROMPTLEDGER_API_KEY_PRIMARY"),
    os.getenv("PROMPTLEDGER_API_KEY_SECONDARY")
]

def make_request_with_fallback(url, json_data):
    for key in API_KEYS:
        if not key:
            continue
        try:
            response = httpx.post(
                url,
                headers={"X-API-Key": key, "Content-Type": "application/json"},
                json=json_data
            )
            if response.status_code != 401:
                return response
        except Exception:
            continue
    raise Exception("All API keys failed")
```

### Sensitive Data Handling

```python
# ❌ Don't log full prompts with PII
print(f"Executing prompt with variables: {variables}")

# ✅ Redact sensitive fields
def redact_sensitive(variables: dict) -> dict:
    sensitive_keys = {"ssn", "credit_card", "password", "email"}
    return {
        k: "[REDACTED]" if k.lower() in sensitive_keys else v
        for k, v in variables.items()
    }

print(f"Executing prompt with variables: {redact_sensitive(variables)}")
```

### Network Security

- Always use HTTPS in production
- Configure firewall rules to restrict PromptLedger access to known IPs
- Use VPN or private networking for internal deployments

---

## Monitoring & Observability

### Health Checks

Integrate PromptLedger health into your monitoring:

```python
def check_promptledger_health():
    try:
        response = httpx.get(f"{API_URL}/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False

# Add to your health check endpoint
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "dependencies": {
            "promptledger": check_promptledger_health()
        }
    }
```

### Execution Metrics

Track key metrics in your application:

```python
from prometheus_client import Counter, Histogram

PROMPT_EXECUTIONS = Counter(
    "promptledger_executions_total",
    "Total prompt executions",
    ["prompt_name", "status", "environment"]
)

PROMPT_LATENCY = Histogram(
    "promptledger_execution_latency_ms",
    "Prompt execution latency",
    ["prompt_name"]
)

def execute_prompt_with_metrics(prompt_name, variables, **kwargs):
    start = time.time()
    try:
        response = httpx.post(
            f"{API_URL}/v1/executions:run",
            headers=headers,
            json={"prompt_name": prompt_name, "variables": variables, **kwargs}
        )
        result = response.json()

        PROMPT_EXECUTIONS.labels(
            prompt_name=prompt_name,
            status=result.get("status", "unknown"),
            environment=kwargs.get("environment", "dev")
        ).inc()

        PROMPT_LATENCY.labels(prompt_name=prompt_name).observe(
            result.get("telemetry", {}).get("latency_ms", 0)
        )

        return result
    except Exception as e:
        PROMPT_EXECUTIONS.labels(
            prompt_name=prompt_name,
            status="error",
            environment=kwargs.get("environment", "dev")
        ).inc()
        raise
```

### Logging Best Practices

```python
import logging
import json

logger = logging.getLogger("promptledger")

def execute_with_logging(prompt_name, variables, **kwargs):
    execution_id = None
    try:
        response = httpx.post(
            f"{API_URL}/v1/executions:run",
            headers=headers,
            json={"prompt_name": prompt_name, "variables": variables, **kwargs}
        )
        result = response.json()
        execution_id = result.get("execution_id")

        logger.info(json.dumps({
            "event": "prompt_execution",
            "prompt_name": prompt_name,
            "execution_id": execution_id,
            "status": result.get("status"),
            "latency_ms": result.get("telemetry", {}).get("latency_ms"),
            "tokens": result.get("telemetry", {}).get("prompt_tokens", 0) +
                      result.get("telemetry", {}).get("response_tokens", 0)
        }))

        return result
    except Exception as e:
        logger.error(json.dumps({
            "event": "prompt_execution_error",
            "prompt_name": prompt_name,
            "execution_id": execution_id,
            "error": str(e)
        }))
        raise
```

---

## Troubleshooting

### Common Issues

#### 401 Unauthorized

```
{"detail": "Invalid API key"}
```

**Solutions**:
- Verify `X-API-Key` header is set correctly
- Check API key hasn't expired or been revoked
- Ensure no leading/trailing whitespace in key

#### 404 Prompt Not Found

```
{"detail": "Prompt 'my_prompt' not found"}
```

**Solutions**:
- Verify prompt name spelling (case-sensitive)
- Check prompt was created with `set_active: true`
- List all prompts: `GET /v1/prompts`

#### 422 Validation Error

```
{"detail": [{"loc": ["body", "variables", "text"], "msg": "field required"}]}
```

**Solutions**:
- Check all template variables are provided
- Verify variable names match template placeholders exactly
- Review template: `GET /v1/prompts/{name}`

#### 500 Provider Error

```
{"detail": "Provider error: Rate limit exceeded"}
```

**Solutions**:
- Implement exponential backoff
- Check your OpenAI API quota
- Use async execution for high-volume workloads

### Debug Mode

Enable verbose logging for troubleshooting:

```python
import httpx
import logging

# Enable httpx debug logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)

# Make request with extended timeout
response = httpx.post(
    f"{API_URL}/v1/executions:run",
    headers=headers,
    json={...},
    timeout=60.0
)
```

### Support Checklist

When requesting support, provide:

1. **Execution ID** (if available)
2. **Trace ID** (for workflow issues)
3. **Error message** (full JSON response)
4. **Timestamp** of the issue
5. **Environment** (dev/staging/production)
6. **Prompt name** involved

---

## API Reference Quick Guide

### Authentication

All requests require:
```
X-API-Key: <your-api-key>
Content-Type: application/json
```

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `PUT` | `/v1/prompts/{name}` | Create/update prompt |
| `GET` | `/v1/prompts/{name}` | Get prompt details |
| `GET` | `/v1/prompts/{name}/versions` | List prompt versions |
| `POST` | `/v1/executions:run` | Synchronous execution |
| `POST` | `/v1/executions:submit` | Async execution |
| `GET` | `/v1/executions/{id}` | Get execution status |
| `GET` | `/v1/traces/{trace_id}/summary` | Get workflow summary |
| `GET` | `/v1/traces/{trace_id}/tree` | Get workflow tree |
| `GET` | `/v1/analytics/prompts` | Get prompt analytics |
| `GET` | `/health` | Health check |

### Execution Request Schema

```json
{
  "prompt_name": "string (required)",
  "environment": "string (default: 'dev')",
  "variables": {"key": "value"},
  "model": {
    "provider": "openai",
    "model_name": "gpt-4o-mini"
  },
  "params": {
    "max_new_tokens": 800,
    "temperature": 0.7,
    "top_p": 0.9
  },
  "trace_id": "string (optional)",
  "parent_span_id": "string (optional)",
  "span_name": "string (optional)",
  "span_kind": "string (optional)"
}
```

---

## Next Steps

1. **Set up development environment**: Follow [Quick Start Integration](#quick-start-integration)
2. **Choose your integration mode**: [Full Management vs Code-Based](#integration-patterns)
3. **Implement workflow tracking**: [Agentic Applications](#workflow-tracking-for-agentic-applications)
4. **Prepare for production**: [Production Deployment](#production-deployment)

### Additional Resources

- [README.md](README.md) - Project overview and quick start
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical architecture details
- [PromptLedger Spec.md](PromptLedger%20Spec.md) - Full API specification
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines

---

*Last Updated: February 2026*
*Integration Guide Version: 1.0*
