# Contributing to PromptLedger

Thanks for your interest in contributing to PromptLedger! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git
- PostgreSQL 15+ (via Docker)
- Redis 7+ (via Docker)

### Getting Started

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/promptledger.git
   cd promptledger
   ```

2. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

   This will automatically run code formatting and linting before each commit.

4. **Start local services**
   ```bash
   # Start PostgreSQL and Redis
   docker-compose up -d postgres redis

   # Run migrations
   alembic upgrade head

   # Seed test data (optional)
   python -m prompt_ledger.scripts.seed_models
   ```

5. **Run the application**
   ```bash
   # Terminal 1: Start API server
   uvicorn prompt_ledger.api.main:app --reload

   # Terminal 2: Start Celery worker
   celery -A prompt_ledger.workers.celery_app worker --loglevel=info
   ```

## Development Rules

PromptLedger follows strict Test-Driven Development (TDD) practices. Please review [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) for detailed guidelines.

### Key Principles

1. **Tests First**: Write tests before implementation
2. **Red-Green-Refactor**: Follow the TDD cycle
3. **High Coverage**: Maintain 90%+ code coverage
4. **Type Safety**: Use type hints throughout

## Code Style

We use automated formatting and linting tools:

- **Black**: Code formatting
- **isort**: Import sorting
- **mypy**: Type checking
- **flake8**: Linting

These are enforced via pre-commit hooks. To run them manually:

```bash
# Format code
black src/ tests/
isort src/ tests/

# Type check
mypy src/

# Lint
flake8 src/ tests/
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=prompt_ledger --cov-report=html

# Run specific test file
pytest tests/test_prompts.py

# Run specific test
pytest tests/test_prompts.py::test_create_prompt
```

### Writing Tests

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Use descriptive test names: `test_<function>_<scenario>_<expected_result>`
- Use fixtures for common setup (see `tests/conftest.py`)

Example:

```python
def test_create_prompt_with_valid_data_returns_prompt_id():
    """Test that creating a prompt with valid data returns a prompt ID."""
    # Arrange
    prompt_data = {...}

    # Act
    result = create_prompt(prompt_data)

    # Assert
    assert result["prompt_id"] is not None
    assert result["version_number"] == 1
```

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Write tests first** (TDD)
   - Write failing tests that describe the desired behavior
   - Run tests to verify they fail: `pytest`

3. **Implement the feature**
   - Write minimal code to make tests pass
   - Run tests to verify: `pytest`

4. **Refactor**
   - Clean up code while keeping tests green
   - Ensure pre-commit hooks pass: `pre-commit run --all-files`

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add feature description"
   ```

   Use [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `test:` Test changes
   - `refactor:` Code refactoring
   - `chore:` Maintenance tasks

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Open a Pull Request**
   - Go to the original repository
   - Click "New Pull Request"
   - Select your fork and branch
   - Fill out the PR template
   - Link related issues

### PR Requirements

Before your PR can be merged:

- ✅ All tests pass
- ✅ Code coverage maintained or improved
- ✅ Pre-commit hooks pass
- ✅ No merge conflicts
- ✅ Documentation updated (if needed)
- ✅ PR template filled out
- ✅ Code review approved

## Reporting Bugs

Found a bug? Please open an issue using the bug report template.

**Before submitting:**
1. Check if the issue already exists
2. Try to reproduce with the latest version
3. Collect relevant information (logs, environment, steps to reproduce)

**Security vulnerabilities**: Please report privately via email (see [SECURITY.md](SECURITY.md))

## Suggesting Features

Have an idea? Open an issue using the feature request template.

**Include:**
- Problem statement: What problem does this solve?
- Proposed solution: How would it work?
- Alternatives: What other approaches did you consider?
- Impact: Who would benefit from this?

## Database Migrations

When making database schema changes:

1. **Create migration**
   ```bash
   alembic revision --autogenerate -m "Description of changes"
   ```

2. **Review generated migration**
   - Check `alembic/versions/` for the new file
   - Verify upgrade and downgrade logic
   - Test both directions

3. **Test migration**
   ```bash
   # Apply
   alembic upgrade head

   # Rollback
   alembic downgrade -1

   # Re-apply
   alembic upgrade head
   ```

4. **Include in PR**
   - Commit the migration file
   - Document breaking changes

## Documentation

### Code Documentation

- Use docstrings for all public functions/classes
- Follow Google style docstrings:

```python
def create_prompt(name: str, template: str) -> Dict[str, Any]:
    """Create a new prompt in the registry.

    Args:
        name: Unique identifier for the prompt
        template: Jinja2 template string

    Returns:
        Dictionary containing prompt_id and version_number

    Raises:
        ValueError: If name is empty or template is invalid
    """
```

### User Documentation

- Update README.md for user-facing changes
- Add examples to `examples/` directory
- Update API documentation (OpenAPI/Swagger)

## Project Structure

```
promptledger/
├── src/prompt_ledger/       # Main source code
│   ├── api/                 # FastAPI endpoints
│   ├── models/              # SQLAlchemy models
│   ├── services/            # Business logic
│   ├── workers/             # Celery tasks
│   └── db/                  # Database utilities
├── tests/                   # Test suite
│   ├── unit/                # Unit tests
│   └── integration/         # Integration tests
├── alembic/                 # Database migrations
├── examples/                # Usage examples
└── docs/                    # Documentation
```

## Getting Help

- 💬 **Discussions**: Use GitHub Discussions for questions
- 🐛 **Issues**: Report bugs via GitHub Issues
- 📧 **Email**: For private inquiries (email TBD)
- 🔗 **Community**: Join our Discord/Slack (links TBD)

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in related blog posts/documentation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to PromptLedger! 🚀
