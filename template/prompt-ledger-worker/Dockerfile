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

# Copy the shared source code and package definition
COPY ../../pyproject.toml .
COPY ../../src .

# Install the local prompt-ledger package
RUN pip install --no-cache-dir .

# Copy the service-specific requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["celery", "-A", "prompt_ledger.workers.celery_app", "worker", "--pool=solo", "--loglevel=info"]
