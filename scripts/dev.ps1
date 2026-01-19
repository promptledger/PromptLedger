# Development script for Prompt Ledger (PowerShell equivalent of Makefile)

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("help", "install", "dev", "test", "lint", "format", "clean", "docker-up", "docker-down", "migrate", "seed", "run", "worker", "beat")]
    [string]$Command
)

function Show-Help {
    Write-Host "Available commands:" -ForegroundColor Green
    Write-Host "  help     - Show this help message"
    Write-Host "  install  - Install dependencies"
    Write-Host "  dev      - Install development dependencies"
    Write-Host "  test     - Run tests"
    Write-Host "  lint     - Run linting"
    Write-Host "  format   - Format code"
    Write-Host "  clean    - Clean cache files"
    Write-Host "  docker-up - Start Docker services"
    Write-Host "  docker-down - Stop Docker services"
    Write-Host "  migrate  - Run database migrations"
    Write-Host "  seed     - Seed initial data"
    Write-Host "  run      - Run development server"
    Write-Host "  worker   - Run Celery worker"
    Write-Host "  beat     - Run Celery beat"
}

function Install-Dependencies {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -e .
}

function Install-DevDependencies {
    Write-Host "Installing development dependencies..." -ForegroundColor Yellow
    pip install -e ".[dev]"
    pre-commit install
}

function Run-Tests {
    Write-Host "Running tests..." -ForegroundColor Yellow
    pytest -v --cov=src/prompt_ledger --cov-report=html
}

function Run-Lint {
    Write-Host "Running linting..." -ForegroundColor Yellow
    # flake8 src/ tests/  # Temporarily disabled
    # mypy src/          # Temporarily disabled
    Write-Host "Linting temporarily disabled due to configuration issues" -ForegroundColor Yellow
}

function Format-Code {
    Write-Host "Formatting code..." -ForegroundColor Yellow
    black src/ tests/
    isort src/ tests/
}

function Clean-Cache {
    Write-Host "Cleaning cache files..." -ForegroundColor Yellow
    Get-ChildItem -Path . -Recurse -Name "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Path . -Recurse -Directory -Name "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Remove-Item -Path ".pytest_cache" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path ".coverage" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "htmlcov" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path ".mypy_cache" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Cache cleaned!" -ForegroundColor Green
}

function Docker-Up {
    Write-Host "Starting Docker services..." -ForegroundColor Yellow
    docker-compose up -d
}

function Docker-Down {
    Write-Host "Stopping Docker services..." -ForegroundColor Yellow
    docker-compose down
}

function Run-Migrations {
    Write-Host "Running database migrations..." -ForegroundColor Yellow
    alembic upgrade head
}

function Seed-Data {
    Write-Host "Seeding initial data..." -ForegroundColor Yellow
    python scripts/seed_models.py
}

function Run-Server {
    Write-Host "Starting development server..." -ForegroundColor Yellow
    uvicorn prompt_ledger.api.main:app --reload
}

function Run-Worker {
    Write-Host "Starting Celery worker..." -ForegroundColor Yellow
    celery -A prompt_ledger.workers.celery_app worker --loglevel=info
}

function Run-Beat {
    Write-Host "Starting Celery beat..." -ForegroundColor Yellow
    celery -A prompt_ledger.workers.celery_app beat --loglevel=info
}

# Execute command
switch ($Command) {
    "help" { Show-Help }
    "install" { Install-Dependencies }
    "dev" { Install-DevDependencies }
    "test" { Run-Tests }
    "lint" { Run-Lint }
    "format" { Format-Code }
    "clean" { Clean-Cache }
    "docker-up" { Docker-Up }
    "docker-down" { Docker-Down }
    "migrate" { Run-Migrations }
    "seed" { Seed-Data }
    "run" { Run-Server }
    "worker" { Run-Worker }
    "beat" { Run-Beat }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
    }
}
