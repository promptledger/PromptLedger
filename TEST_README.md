# Prompt Ledger Test Suite

This document provides a comprehensive overview of the Prompt Ledger test suite and instructions for executing tests.

## Table of Contents

- [Overview](#overview)
- [Test Categories](#test-categories)
- [Running Tests](#running-tests)
- [Test Environment](#test-environment)
- [Test Coverage](#test-coverage)
- [Troubleshooting](#troubleshooting)

## Overview

The Prompt Ledger project follows strict Test-Driven Development (TDD) principles with comprehensive test coverage including:

- **44 tests total** (as of latest run)
- Unit tests for individual components
- Integration tests for API endpoints
- Model validation tests
- Database schema tests

All tests must pass before any code changes are merged.

## Test Categories

### 1. Model Tests (`tests/test_models.py`)
**Purpose**: Test SQLAlchemy model definitions, relationships, and constraints.

**Tests**:
- `test_compute_checksum` - Verifies checksum calculation for prompt templates
- `test_prompt_creation` - Tests Prompt model creation and validation
- `test_prompt_version_creation` - Tests PromptVersion model relationships
- `test_execution_creation` - Tests Execution model creation
- `test_model_creation` - Tests Model creation and relationships

### 2. Prompt Mode Tests (`tests/unit/test_models_prompt_mode.py`)
**Purpose**: Test the dual-mode prompt functionality (full vs tracking mode).

**Tests**:
- `test_prompt_defaults_to_full_mode` - Verifies default mode is 'full'
- `test_prompt_can_be_created_with_tracking_mode` - Tests tracking mode creation
- `test_prompt_mode_can_be_queried` - Tests mode field querying
- `test_mode_index_exists` - Verifies performance index exists
- `test_mode_field_not_nullable` - Tests database constraint enforcement
- `test_full_and_tracking_prompts_can_have_same_version_structure` - Tests version compatibility

### 3. Service Tests (`tests/unit/test_prompt_service.py`)
**Purpose**: Test business logic in service layer.

**Tests**:
- Prompt service functionality for both full and tracking modes
- Code-based prompt registration
- Version management

### 4. Integration Tests (`tests/integration/test_code_prompts_api.py`)
**Purpose**: Test API endpoints and complete workflows.

**Test Classes**:
- `TestRegisterCodePrompts` - Code prompt registration endpoints
- `TestExecuteCodePrompt` - Prompt execution endpoints
- `TestPromptHistory` - Prompt history and retrieval endpoints

**Key Scenarios**:
- Register new code prompts
- Detect content changes
- Execute tracking mode prompts
- Handle full mode prompt restrictions
- Retrieve prompt history

### 5. API Tests (`tests/test_prompts.py`)
**Purpose**: Test REST API endpoints for prompt management.

**Tests**:
- Prompt CRUD operations
- Version management
- Content change detection

## Running Tests

### Prerequisites

1. **Docker Desktop** must be running
2. **Docker Compose** installed
3. All services up and running

### Start Test Environment

```bash
# Start all services
docker-compose up -d

# Verify services are healthy
docker-compose ps
```

### Execute Tests

#### Run All Tests
```bash
# Run full test suite
docker-compose exec api python -m pytest tests/ -v

# Run with quiet output
docker-compose exec api python -m pytest tests/ --tb=no -q
```

#### Run Specific Test Categories
```bash
# Run only model tests
docker-compose exec api python -m pytest tests/test_models.py -v

# Run only integration tests
docker-compose exec api python -m pytest tests/integration/ -v

# Run only unit tests
docker-compose exec api python -m pytest tests/unit/ -v
```

#### Run Individual Tests
```bash
# Run specific test
docker-compose exec api python -m pytest tests/test_models.py::TestPromptModel::test_prompt_creation -v

# Run with detailed output
docker-compose exec api python -m pytest tests/integration/test_code_prompts_api.py::TestExecuteCodePrompt::test_execute_tracking_mode_prompt_sync -v -s
```

### Test Output Options

```bash
# Verbose output with test names
docker-compose exec api python -m pytest tests/ -v

# Show short traceback on failure
docker-compose exec api python -m pytest tests/ --tb=short

# No traceback (quiet mode)
docker-compose exec api python -m pytest tests/ --tb=no

# Stop on first failure
docker-compose exec api python -m pytest tests/ -x

# Run with coverage (if coverage is installed)
docker-compose exec api python -m pytest tests/ --cov=src --cov-report=html
```

## Test Environment

### Database Configuration

Tests use a separate PostgreSQL database:

- **Database**: `prompt_ledger_test`
- **Connection**: `postgresql+asyncpg://postgres:password@postgres:5432/prompt_ledger_test`
- **Isolation**: Each test gets a fresh database schema

### Environment Variables

The test environment uses these key environment variables (configured in `docker-compose.yml`):

```yaml
environment:
  - TEST_DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/prompt_ledger_test
  - DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/prompt_ledger
```

### Test Fixtures

Key fixtures in `tests/conftest.py`:

- `db_session` - Provides fresh database session for each test
- `client` - Provides HTTP client for API testing
- `full_prompt` - Creates a full-mode prompt for testing
- `tracking_prompt` - Creates a tracking-mode prompt for testing

### Test Data Management

- Each test runs in isolation with a clean database
- Schema is created before each test and dropped after
- Test data doesn't persist between tests
- Uses async SQLAlchemy sessions for database operations

## Test Coverage

### Current Coverage (44 tests)

| Category | Tests | Focus |
|----------|-------|-------|
| Model Tests | 5 | SQLAlchemy models, relationships |
| Mode Tests | 6 | Dual-mode functionality |
| Service Tests | 4 | Business logic |
| Integration Tests | 19 | API endpoints, workflows |
| API Tests | 10 | REST API operations |

### Coverage Requirements

- **90%+ minimum coverage** required for all code
- **Unit tests** for all business logic
- **Integration tests** for all API endpoints
- **Model tests** for all database entities

## Troubleshooting

### Common Issues

#### 1. "Database connection failed"
```bash
# Solution: Ensure PostgreSQL container is running
docker-compose ps
docker-compose restart postgres
```

#### 2. "Tests directory not found"
```bash
# Solution: Ensure tests volume is mounted correctly
docker-compose down
docker-compose up -d
```

#### 3. "pytest not found"
```bash
# Solution: Ensure dev dependencies are installed
docker-compose exec api pip install -e ".[dev]"
```

#### 4. "Async connection errors"
```bash
# Solution: Restart containers to clear connection pools
docker-compose restart api
```

#### 5. "Environment variable not set"
```bash
# Solution: Check docker-compose.yml for TEST_DATABASE_URL
docker-compose exec api env | grep TEST_DATABASE_URL
```

### Debug Mode

For debugging failing tests:

```bash
# Run with verbose output and stop on failure
docker-compose exec api python -m pytest tests/ -v -x --tb=long

# Run specific test with debug output
docker-compose exec api python -m pytest tests/integration/test_code_prompts_api.py::TestExecuteCodePrompt::test_execute_tracking_mode_prompt_sync -v -s --tb=long
```

### Performance Considerations

- Tests run in parallel by default for faster execution
- Database operations use connection pooling
- Each test gets isolated database schema
- Consider using `-x` flag to stop on first failure during development

## TDD Compliance

This project enforces strict TDD rules:

1. **Write tests first** - No production code without failing tests
2. **Red-Green-Refactor** - Follow the TDD cycle
3. **90% coverage** - Minimum coverage requirement
4. **Pre-commit hooks** - Tests must pass before commits
5. **CI pipeline** - Automated testing on all PRs

## Contributing

When adding new features:

1. Write failing tests first
2. Implement minimal code to pass tests
3. Refactor while maintaining test coverage
4. Ensure all tests pass before submitting PR
5. Add integration tests for new API endpoints

## Test Commands Reference

```bash
# Quick test run (development)
docker-compose exec api python -m pytest tests/ -q

# Full test run (CI/verification)
docker-compose exec api python -m pytest tests/ -v --tb=short

# Run specific test file
docker-compose exec api python -m pytest tests/test_models.py -v

# Run with coverage report
docker-compose exec api python -m pytest tests/ --cov=src --cov-report=term-missing

# Debug failing test
docker-compose exec api python -m pytest tests/path/to/test.py::test_name -v -s --tb=long
```

---

**Last Updated**: January 19, 2026
**Test Count**: 44 tests passing
**Coverage**: 90%+ maintained across all modules
