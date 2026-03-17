# Feature Request: One-Click Deployment Templates

**FR-002** | **Priority:** High | **Status:** Proposed
**Author:** Development Team | **Date:** January 21, 2026

---

## Executive Summary

To accelerate adoption and simplify onboarding, this feature request proposes creating one-click deployment templates for popular PaaS providers, starting with Railway. This will enable GenAI practitioners to deploy the entire PromptLedger stack (API, worker, PostgreSQL, Redis) to their own cloud account in minutes, drastically reducing the setup friction from the current manual `docker-compose` process.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Requirements](#requirements)
3. [Why This Matters](#why-this-matters)
4. [Proposed Alternatives](#proposed-alternatives)
5. [Pairwise Analysis](#pairwise-analysis)
6. [Recommendation](#recommendation)
7. [Appendix](#appendix)

---

## Problem Statement

### Current State

Deploying PromptLedger requires a user to manually clone the repository, configure environment variables, and run `docker-compose up`. They must also manually run `alembic upgrade head` to initialize the database schema. This process, while standard for experienced DevOps engineers, presents a significant barrier to entry for the target audience: GenAI practitioners, data scientists, and developers who want to quickly evaluate or use the service without extensive infrastructure setup.

### The Gap

There is no simple, automated way for a user to deploy their own instance of PromptLedger. This friction leads to high drop-off rates between initial interest and successful deployment.

| Question | Current Capability |
|---|---|
| "How can I try PromptLedger in 5 minutes?" | ❌ Not possible; requires 30-60 mins of manual setup |
| "Can I deploy this to my own cloud account easily?" | ❌ Requires significant manual configuration |
| "How do I set up the database and migrations?" | ❌ Manual `alembic` commands required |

### Constraints

1.  The solution must support the existing multi-service architecture (API, worker, beat, postgres, redis).
2.  The process must be self-service, requiring minimal input from the user beyond necessary secrets (e.g., `OPENAI_API_KEY`).
3.  The templates must be maintainable and reflect updates to the core application.

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Create a one-click deployment template for Railway | Must Have |
| FR-2 | The template must provision all required services: `api`, `worker`, `beat` | Must Have |
| FR-3 | The template must provision required backing services: PostgreSQL and Redis | Must Have |
| FR-4 | The template must automatically run database migrations (`alembic upgrade head`) on initial deploy | Must Have |
| FR-5 | The template must prompt the user for required environment variables (`OPENAI_API_KEY`, `API_KEY`) | Must Have |
| FR-6 | Add a "Deploy on Railway" button to the `README.md` | Must Have |
| FR-7 | Create a one-click deployment template for Render | Should Have |
| FR-8 | Create a one-click deployment template for Heroku | Could Have |

### Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Deployment from template to running application should take < 10 minutes | Usability |
| NFR-2 | The configuration files (`railway.toml`, `render.yaml`) must be stored in the project repository | Maintainability |
| NFR-3 | The solution should leverage the existing `docker-compose.yml` where possible to reduce configuration duplication | Simplicity |

---

## Why This Matters

1.  **Reduced Time-to-Value**: Drastically cuts the time from discovery to a working application from an hour to minutes, leading to higher user activation.
2.  **Increased Adoption**: By making PromptLedger easy to deploy, we expand our user base beyond DevOps experts to the broader GenAI community.
3.  **Competitive Parity**: Most successful open-source infrastructure projects (e.g., Supabase, Appwrite, Ghost) offer one-click deployment options on major platforms.
4.  **Enables Monetization**: The one-click template serves as the "free, self-hosted" tier, acting as the top of the funnel for future paid offerings like a managed SaaS version, enterprise licenses, or support contracts.
5.  **Marketing Asset**: The "Deploy on..." buttons are a powerful marketing tool, signaling that the project is mature, easy to use, and production-ready.

---

## Proposed Alternatives

### Option A: Railway Only (MVP)

-   **Description**: Create a `railway.toml` file and a deployment button targeting only Railway. Railway has excellent support for `docker-compose.yml`, making it a natural first choice.
-   **Pros**: Fastest to implement, validates the one-click concept, Railway is popular with the target developer audience.
-   **Cons**: Ignores users on other platforms.
-   **Effort**: ~1 day

### Option B: Railway + Render (Recommended)

-   **Description**: Implement one-click templates for both Railway (`railway.toml`) and Render (`render.yaml`). Render Blueprints are also very powerful and can define the entire stack in one file.
-   **Pros**: Covers two of the most popular and developer-friendly PaaS providers. Captures a significantly larger audience.
-   **Cons**: Requires maintaining two separate configuration files.
-   **Effort**: ~2 days

### Option C: Multi-Platform (Railway, Render, Heroku)

-   **Description**: Add support for Heroku via an `app.json` file in addition to Railway and Render.
-   **Pros**: Maximum reach and visibility by targeting three major platforms.
-   **Cons**: Highest maintenance burden. Heroku's model is less suited to this stack (e.g., Redis is a third-party add-on, not a native service), leading to a less smooth user experience.
-   **Effort**: ~4 days

---

## Pairwise Analysis

### Option A vs. B: Railway vs. Railway + Render

-   **Verdict**: Option B is superior. The effort to add Render support is minimal once the Railway logic is established. The `render.yaml` is conceptually similar, and the return on investment in terms of audience reach is high.

### Option B vs. C: Adding Heroku

-   **Verdict**: Option B is the pragmatic choice. While Heroku has a large user base, the friction of its add-on system for Redis and the limitations of `app.json` for multi-process workers make it a less-than-ideal experience. The maintenance cost of a third template outweighs the benefits for an initial release. Heroku should be a fast-follow, not part of the initial push.

---

## Recommendation

### Primary Recommendation: Option B (Railway + Render)

**Rationale:**
1.  **High ROI**: For the small additional effort of creating a `render.yaml`, we double our potential user base among modern PaaS platforms.
2.  **Developer Experience**: Both Railway and Render offer a first-class developer experience for `docker-compose`-based applications, aligning well with our existing setup.
3.  **Maintainability**: Managing two YAML files (`railway.toml` and `render.yaml`) is a reasonable maintenance burden.

### Implementation Strategy

**Phase 1 (MVP): Railway Template (~1 day)**
1.  Create and test `railway.toml` to configure the build and deploy commands.
2.  Generate the Railway deployment button URL.
3.  Add the button and documentation to `README.md`.

**Phase 2 (Fast-Follow): Render Template (~1 day)**
1.  Create and test `render.yaml` to define all services and databases.
2.  Generate the Render deployment button.
3.  Add the second button to `README.md`.

**Phase 3 (Post-MVP): Heroku**
-   Investigate the best user experience for a Heroku deployment, including clear documentation for the Redis add-on requirement.
-   Create `app.json` and add the button.

---

---

## Step-by-Step Deployment Instructions

### Phase 1: Railway Template Creation

#### Step 1: Prepare the Repository

Before creating the Railway template, ensure the repository is properly configured:

1. **Create a clean deployment branch** (optional but recommended):
   ```bash
   git checkout -b railway-template
   ```

2. **Review and update the Dockerfile** to ensure it's optimized for Railway deployment:
   - Ensure health check endpoint exists at `/health`
   - Verify all dependencies are properly specified
   - Confirm the start command is configurable via environment variables

3. **Verify docker-compose.yml** includes all required services:
   - API service
   - Worker service
   - Beat (scheduler) service
   - PostgreSQL database
   - Redis cache

#### Step 2: Access Railway Template Creator

1. Log in to [Railway](https://railway.com)
2. Navigate to your workspace
3. Go to [Templates page](https://railway.com/workspace/templates)
4. Click **"New Template"** button

#### Step 3: Configure Template Services

**Service 1: PostgreSQL Database**

1. Click **"Add New"** → Select **"Database"** → Choose **"PostgreSQL"**
2. Service name: `PostgreSQL`
3. **Settings tab**:
   - No additional settings needed (Railway provides defaults)
4. **Add Volume**:
   - Right-click service → **"Attach Volume"**
   - Mount path: `/var/lib/postgresql/data`
   - This ensures data persistence across deployments

**Service 2: Redis Cache**

1. Click **"Add New"** → Select **"Database"** → Choose **"Redis"**
2. Service name: `Redis`
3. **Add Volume**:
   - Right-click service → **"Attach Volume"**
   - Mount path: `/data`
   - This ensures cache persistence

**Service 3: API Service**

1. Click **"Add New"** → Select **"GitHub Repo"**
2. Enter repository URL: `https://github.com/yourusername/PromptLedger`
3. Service name: `PromptLedger API`
4. **Variables tab** - Add the following environment variables:

   | Variable | Value | Description |
   |----------|-------|-------------|
   | `DATABASE_URL` | `postgresql://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}` | PostgreSQL connection string using reference variables |
   | `REDIS_URL` | `redis://${{Redis.RAILWAY_PRIVATE_DOMAIN}}:6379` | Redis connection string using private networking |
   | `OPENAI_API_KEY` | (leave empty) | User must provide - Add description: "Your OpenAI API key for LLM operations" |
   | `API_KEY` | `${{secret(32)}}` | Auto-generated secure API key using template function |
   | `SECRET_KEY` | `${{secret(64)}}` | Auto-generated secret for session encryption |
   | `PORT` | `8000` | Port for the API server |
   | `ENVIRONMENT` | `production` | Deployment environment |

5. **Settings tab**:
   - **Root Directory**: Leave empty (unless using monorepo)
   - **Start Command**: `alembic upgrade head && uvicorn prompt_ledger.api.main:app --host 0.0.0.0 --port $PORT`
   - **Healthcheck Path**: `/health`
   - **Enable Public Networking**: Toggle ON → Select **"HTTP"**
   - **Custom Domain** (optional): Can be configured post-deployment

**Service 4: Celery Worker**

1. Click **"Add New"** → Select **"GitHub Repo"**
2. Enter same repository URL: `https://github.com/yourusername/PromptLedger`
3. Service name: `PromptLedger Worker`
4. **Variables tab** - Add the following (using reference variables):

   | Variable | Value | Description |
   |----------|-------|-------------|
   | `DATABASE_URL` | `${{PromptLedger API.DATABASE_URL}}` | Reference API service database URL |
   | `REDIS_URL` | `${{PromptLedger API.REDIS_URL}}` | Reference API service Redis URL |
   | `OPENAI_API_KEY` | `${{PromptLedger API.OPENAI_API_KEY}}` | Reference API service OpenAI key |
   | `API_KEY` | `${{PromptLedger API.API_KEY}}` | Reference API service key |

5. **Settings tab**:
   - **Start Command**: `celery -A prompt_ledger.workers.celery_app worker --loglevel=info`
   - **Public Networking**: Toggle OFF (worker doesn't need public access)

**Service 5: Celery Beat (Scheduler)**

1. Click **"Add New"** → Select **"GitHub Repo"**
2. Enter same repository URL: `https://github.com/yourusername/PromptLedger`
3. Service name: `PromptLedger Beat`
4. **Variables tab** - Use same reference variables as Worker
5. **Settings tab**:
   - **Start Command**: `celery -A prompt_ledger.workers.celery_app beat --loglevel=info`
   - **Public Networking**: Toggle OFF

#### Step 4: Configure Template Metadata

1. **Template Name**: `PromptLedger`
2. **Template Icon**: Upload a 1:1 ratio logo with transparent background
3. **Service Icons**:
   - API: PromptLedger logo
   - Worker: Celery logo
   - Beat: Celery logo
   - PostgreSQL: PostgreSQL logo (Railway provides default)
   - Redis: Redis logo (Railway provides default)

#### Step 5: Create Template Overview

Click on **"Overview"** section and add the following markdown:

```markdown
# Deploy and Host PromptLedger with Railway

PromptLedger is a comprehensive prompt execution and lineage tracking system designed for GenAI engineers. It provides complete visibility into your AI application's prompt flow, execution history, and performance metrics. Track every prompt, response, and workflow execution with automatic versioning, making debugging and optimization straightforward.

## About Hosting PromptLedger

Hosting PromptLedger requires a complete stack including a FastAPI backend, PostgreSQL database for prompt storage, Redis for task queuing, and Celery workers for asynchronous processing. Railway handles all of these components seamlessly with automatic scaling, private networking between services, and built-in monitoring. The platform takes care of database migrations, SSL certificates, and environment configuration, letting you focus on building your GenAI applications.

## Common Use Cases

- **Prompt Engineering Workflows**: Track and version every prompt iteration across your team
- **GenAI Application Debugging**: Trace complete execution paths from initial prompt to final output
- **Performance Monitoring**: Analyze token usage, latency, and cost metrics across all LLM calls
- **Compliance & Audit Trails**: Maintain complete records of all AI interactions for regulatory requirements
- **A/B Testing**: Compare different prompt strategies with detailed execution data

## Dependencies for PromptLedger Hosting

- **PostgreSQL** - Primary database for storing prompts, executions, and lineage data
- **Redis** - Message broker and caching layer for Celery task queue
- **Celery** - Distributed task queue for asynchronous workflow processing
- **FastAPI** - High-performance API framework for the backend service
- **Docker** - Containerization for consistent deployments

### Deployment Dependencies

- [PromptLedger GitHub Repository](https://github.com/yourusername/PromptLedger)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

### Why Deploy PromptLedger on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying PromptLedger on Railway, you are one step closer to supporting a complete full-stack GenAI application with minimal burden. Host your API servers, databases, AI agents, and more on Railway.
```

#### Step 6: Finalize and Save Template

1. Review all service configurations
2. Verify all reference variables are correctly linked
3. Click **"Create Template"**
4. You will be redirected to your Templates page
5. Copy the template URL (format: `https://railway.com/new/template/XXXXXX`)

#### Step 7: Publish Template (Optional)

To make your template available in the Railway marketplace:

1. From your Templates page, find the PromptLedger template
2. Click **"Publish"**
3. Fill out the publishing form:
   - **Category**: Developer Tools / Infrastructure
   - **Tags**: genai, prompt-engineering, observability, fastapi, python
   - **Demo Project** (optional): Link to a live demo instance
4. Submit for review

**Note**: Published templates are eligible for Railway's [Kickback Program](https://railway.com/kickback), where you can earn up to 50% revenue share from template deployments.

#### Step 8: Add "Deploy on Railway" Button to README

1. Create or update `README.md` in your repository
2. Add the button at the top of the file:

```markdown
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/XXXXXX?utm_medium=integration&utm_source=button&utm_campaign=promptledger)
```

Replace `XXXXXX` with your actual template code.

3. Commit and push the changes:
```bash
git add README.md
git commit -m "docs: add Deploy on Railway button"
git push origin main
```

### Phase 2: Testing the Template

#### Step 1: Test Deployment

1. Click your own "Deploy on Railway" button
2. **Configure Required Variables**:
   - Enter your `OPENAI_API_KEY`
   - Review auto-generated `API_KEY` (can regenerate if needed)
3. Click **"Deploy"**
4. Wait for all services to deploy (typically 3-5 minutes)

#### Step 2: Verify Services

1. **Check PostgreSQL**:
   - Navigate to PostgreSQL service
   - Verify it's running
   - Check that volume is attached

2. **Check Redis**:
   - Navigate to Redis service
   - Verify it's running
   - Confirm volume is attached

3. **Check API Service**:
   - Navigate to API service
   - Click on the generated public URL
   - Verify `/health` endpoint returns 200 OK
   - Check deployment logs for successful migration: `Running alembic upgrade head`

4. **Check Worker Service**:
   - Navigate to Worker service
   - Check logs for: `celery@worker ready`
   - Verify it's connected to Redis

5. **Check Beat Service**:
   - Navigate to Beat service
   - Check logs for: `Scheduler: Sending due task`

#### Step 3: Functional Testing

1. **Test API Endpoint**:
   ```bash
   curl -X GET https://your-api-url.railway.app/health \
     -H "X-API-Key: your-api-key"
   ```

2. **Test Prompt Execution**:
   ```bash
   curl -X POST https://your-api-url.railway.app/api/v1/prompts/execute \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your-api-key" \
     -d '{
       "prompt_text": "What is the capital of France?",
       "model": "gpt-3.5-turbo"
     }'
   ```

3. **Verify Database Records**:
   - Check Railway PostgreSQL service logs
   - Confirm prompt execution was recorded

#### Step 4: Performance Testing

1. Navigate to Railway project **"Metrics"** tab
2. Monitor:
   - API response times
   - Database connection pool usage
   - Redis memory usage
   - Worker task throughput

### Phase 3: Maintenance and Updates

#### Updating the Template

When you need to update the template with new features:

1. Go to [Templates page](https://railway.com/workspace/templates)
2. Click **"Edit"** on your PromptLedger template
3. Make necessary changes to:
   - Service configurations
   - Environment variables
   - Start commands
   - Overview documentation
4. Click **"Save Template"**

**Note**: Users who have already deployed the template will receive notifications about upstream updates via GitHub pull requests (if using the updatable templates feature).

#### Template Best Practices Checklist

- ✅ **Icons**: 1:1 aspect ratio with transparent backgrounds
- ✅ **Naming**: Follow proper capitalization (PromptLedger, not promptledger)
- ✅ **Private Networking**: All service-to-service communication uses `RAILWAY_PRIVATE_DOMAIN`
- ✅ **Environment Variables**: Include descriptions for all variables
- ✅ **Secrets**: Use `${{secret()}}` function, never hardcode
- ✅ **Reference Variables**: Use `${{ServiceName.VARIABLE}}` to avoid duplication
- ✅ **Health Checks**: Configure readiness checks for all web services
- ✅ **Persistent Storage**: Attach volumes to PostgreSQL and Redis
- ✅ **Authentication**: Generate secure credentials automatically
- ✅ **Documentation**: Clear overview with use cases and setup instructions

---

## Appendix

### A. Example `railway.toml` (Alternative Configuration Method)

While Railway templates are typically created via the web UI, you can also define configuration in code:

```toml
[build]
builder = "dockerfile"

[deploy]
startCommand = "alembic upgrade head && uvicorn prompt_ledger.api.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 120
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

### B. Railway Template Variable Functions

Template variable functions for generating secure values:

```bash
# Generate 32-character random secret
${{secret(32)}}

# Generate 64-character hex secret (like openssl rand -hex 32)
${{secret(64, "abcdef0123456789")}}

# Generate random integer between 1000-9999
${{randomInt(1000, 9999)}}

# Generate UUID-like string
${{secret(8, "0123456789abcdef")}}-${{secret(4, "0123456789abcdef")}}-4${{secret(3, "0123456789abcdef")}}-${{secret(1, "89ab")}}${{secret(3, "0123456789abcdef")}}-${{secret(12, "0123456789abcdef")}}
```

### C. Example Reference Variables

Use reference variables to avoid duplication and ensure consistency:

```bash
# Reference another service's database URL
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Reference the API service's OpenAI key in worker
OPENAI_API_KEY=${{PromptLedger API.OPENAI_API_KEY}}

# Reference the private domain for internal communication
REDIS_URL=redis://${{Redis.RAILWAY_PRIVATE_DOMAIN}}:6379
```

### D. Example `render.yaml` (For Future Render Support)

```yaml
services:
  - type: web
    name: prompt-ledger-api
    env: docker
    repo: https://github.com/your-org/prompt-ledger
    dockerCommand: alembic upgrade head && uvicorn prompt_ledger.api.main:app --host 0.0.0.0 --port $PORT
    healthCheck:
      path: /health
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: prompt-ledger-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: prompt-ledger-redis
          property: connectionString
      - key: OPENAI_API_KEY
        sync: false
      - key: API_KEY
        generateValue: true

  - type: worker
    name: prompt-ledger-worker
    env: docker
    repo: https://github.com/your-org/prompt-ledger
    dockerCommand: celery -A prompt_ledger.workers.celery_app worker --loglevel=info
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: prompt-ledger-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: prompt-ledger-redis
          property: connectionString
      - key: OPENAI_API_KEY
        sync: false

databases:
  - name: prompt-ledger-db
    databaseName: prompt_ledger
    user: prompt_ledger_user

  - name: prompt-ledger-redis
    plan: free
```

### E. User Stories

> **As a GenAI developer**, I want to deploy a personal instance of PromptLedger to my own cloud account in under 10 minutes, without writing any infrastructure code, so that I can immediately start tracking my prompts.

> **As a platform engineer**, I want to provide my team with a one-click deployment solution for PromptLedger so they can spin up isolated environments for testing without requiring DevOps support.

> **As an open-source maintainer**, I want to offer a Railway template so potential users can try PromptLedger with minimal friction, increasing adoption and community engagement.

### F. Troubleshooting Common Issues

**Issue**: Database migrations fail on first deploy
- **Solution**: Ensure `alembic upgrade head` runs before the main application starts in the start command

**Issue**: Worker can't connect to Redis
- **Solution**: Verify `REDIS_URL` uses `RAILWAY_PRIVATE_DOMAIN` and not public domain

**Issue**: API returns 502 Bad Gateway
- **Solution**: Check health check endpoint is accessible and returns 200 within timeout period

**Issue**: Environment variables not populating
- **Solution**: Ensure reference variable syntax is correct: `${{ServiceName.VARIABLE}}`

**Issue**: Volume not persisting data
- **Solution**: Verify volume mount path matches the service's expected data directory
