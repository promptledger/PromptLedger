# Prompt Ledger Makefile

.PHONY: help install dev test lint format clean docker-up docker-down migrate seed

# Default target
help:
	@echo "Available commands:"
	@echo "  install     Install dependencies"
	@echo "  dev         Install development dependencies"
	@echo "  test        Run tests"
	@echo "  lint        Run linting"
	@echo "  format      Format code"
	@echo "  clean       Clean cache files"
	@echo "  docker-up   Start Docker services"
	@echo "  docker-down Stop Docker services"
	@echo "  migrate     Run database migrations"
	@echo "  seed        Seed initial data"

# Installation
install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pre-commit install

# Development
test:
	pytest -v --cov=src/prompt_ledger --cov-report=html

lint:
	flake8 src/ tests/
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/

# Docker
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Database
migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(MSG)"

seed:
	python scripts/seed_models.py

# Development server
run:
	uvicorn prompt_ledger.api.main:app --reload

worker:
	celery -A prompt_ledger.workers.celery_app worker --loglevel=info

beat:
	celery -A prompt_ledger.workers.celery_app beat --loglevel=info
