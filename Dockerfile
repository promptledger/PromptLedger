# Multi-stage build for Python application
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home --shell /bin/bash app

# Set work directory
WORKDIR /app

# Copy requirements first
COPY pyproject.toml ./
COPY README.md ./

# Copy application code (needed for editable install)
COPY src/ ./src/
COPY tests/ ./tests/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/
COPY entrypoint.sh ./

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -e ".[dev]"

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Change ownership to app user
RUN chown -R app:app /app
USER app

# Expose port
EXPOSE 8000

# Use entrypoint script for Railway compatibility
ENTRYPOINT ["./entrypoint.sh"]
