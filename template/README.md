# PromptLedger Railway Template

This template provides a one-click deployment of PromptLedger on Railway, giving you a powerful, centralized prompt management and execution service.

## What's Included

This template deploys the following services:

- **`prompt-ledger-api`**: The core FastAPI application that provides the PromptLedger API.
- **`prompt-ledger-worker`**: A Celery worker for asynchronous prompt execution.
- **`sample-app`**: A simple FastAPI application demonstrating how to integrate with PromptLedger.
- **`PostgreSQL`**: A database for storing prompts, versions, and execution history.
- **`Redis`**: A broker for the Celery worker.

## How to Use

1.  Click the "Deploy to Railway" button.
2.  Provide the required environment variables (see below).
3.  Once deployed, the `sample-app` will be available at its public URL. You can test the PromptLedger integration by navigating to the `/welcome` endpoint.

## Environment Variables

-   **`OPENAI_API_KEY`**: Your API key for OpenAI. This is required for executing prompts with OpenAI models.

## Service Details

### `prompt-ledger-api`

-   **Public URL**: `https://prompt-ledger-api-${RAILWAY_PROJECT_ID}.up.railway.app`
-   **Health Check**: `/health`
-   **Database Migrations**: Alembic migrations are automatically applied on deploy.

### `sample-app`

-   **Public URL**: `https://sample-app-${RAILWAY_PROJECT_ID}.up.railway.app`
-   **Endpoints**:
    -   `/`: Displays a welcome message.
    -   `/welcome`: Executes a sample prompt using PromptLedger.
