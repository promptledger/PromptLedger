#!/bin/sh
set -e

# Use PORT environment variable with fallback to 8000
PORT=${PORT:-8000}

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Start the application
echo "Starting PromptLedger API on port $PORT..."
exec uvicorn prompt_ledger.api.main:app --host 0.0.0.0 --port $PORT
