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

# Copy application code and all other necessary files
COPY . .

# Install dependencies including the local prompt-ledger package
RUN pip install --no-cache-dir -r requirements.txt

CMD ["celery", "-A", "prompt_ledger.workers.celery_app", "worker", "--pool=solo", "--loglevel=info"]
