#!/bin/bash
echo "Running database migrations..."
alembic upgrade head
echo "Starting API server on port ${PORT:-8000}..."
exec uvicorn prompt_ledger.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
