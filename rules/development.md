# Development Rules & Guidelines

## Core Principles

### 1. Test-Driven Development (TDD) - MANDATORY ⚡
**This rule is non-negotiable and must be followed for ALL changes:**

- **Red-Green-Refactor Cycle**: Always write tests first, watch them fail (red), implement code to make them pass (green), then refactor.
- **No Code Without Tests**: Never write production code without first writing failing tests.
- **Feature Test First**: For any new feature, write the acceptance/integration test first.
- **Unit Test Coverage**: Every function, method, and class must have corresponding unit tests.
- **Test Commitment**: Tests are committed along with the implementation code in the same PR.

### 2. Code Quality Standards

#### Code Style
- Follow PEP 8 and project-specific formatting rules
- Use `black` for code formatting, `isort` for imports
- Maximum line length: 88 characters
- Use type hints everywhere possible

#### Documentation
- All public functions and classes must have docstrings
- Docstrings follow Google style format
- Complex logic must have inline comments explaining the "why"
- API endpoints must have OpenAPI descriptions

#### Error Handling
- Use specific exception types, never bare `except:`
- Log errors with appropriate context and severity
- Provide meaningful error messages to API consumers
- Implement graceful degradation where possible

### 3. Architecture Guidelines

#### Database
- All database operations must use async sessions
- Use Alembic for all schema changes
- Never use raw SQL queries - always use SQLAlchemy ORM
- Implement proper foreign key constraints and indexes

#### API Design
- Follow RESTful principles
- Use appropriate HTTP status codes
- Implement proper authentication and authorization
- Rate limiting and validation for all endpoints

#### Async Operations
- All I/O operations must be async
- Use proper async context managers
- Implement timeout handling for external API calls
- Use connection pooling for database and Redis

### 4. Security Requirements

- Never commit API keys, secrets, or sensitive data
- Use environment variables for all configuration
- Implement proper input validation and sanitization
- Follow OWASP security guidelines
- Regular security audits and dependency updates

### 5. Performance Standards

- Database queries must be optimized with proper indexes
- Implement caching for frequently accessed data
- Monitor and log performance metrics
- Load testing for all critical endpoints
- Memory and CPU usage monitoring

### 6. Git & Collaboration Rules

#### Commit Standards
- Use conventional commit format: `type(scope): description`
- Each commit must be logically atomic and testable
- Never commit broken tests or failing builds
- Include issue/story references in commits

#### Branch Strategy
- Feature branches from `main`
- Descriptive branch names: `feature/prompt-versioning`, `fix/auth-validation`
- Keep branches small and focused
- Regular merges to avoid conflicts

#### Pull Request Requirements
- All PRs must pass automated tests
- Code review is mandatory for all changes
- Update documentation for API changes
- Include test coverage reports

### 7. Testing Requirements

#### Test Types
- **Unit Tests**: Test individual functions and classes in isolation
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete user workflows
- **Performance Tests**: Load and stress testing

#### Test Standards
- Minimum 90% code coverage
- All tests must be deterministic (no random failures)
- Use descriptive test names that explain the scenario
- Test both happy path and error conditions
- Mock external dependencies appropriately

#### Test Data
- Use factories for test data generation
- Clean up test data after each test
- Never use production data in tests
- Test with realistic data volumes

### 8. Monitoring & Observability

- Structured logging with correlation IDs
- Metrics for all critical operations
- Health checks for all services
- Alerting for error rates and performance issues
- Distributed tracing for async operations

### 9. Deployment & DevOps

#### Environment Management
- Separate configs for dev/staging/prod
- Infrastructure as code for all environments
- Blue-green deployments for zero downtime
- Automated rollback capabilities

#### CI/CD Requirements
- Automated testing on every commit
- Security scanning in CI pipeline
- Automated dependency vulnerability checks
- Deployment only after all checks pass

### 10. Documentation Standards

#### Code Documentation
- README with setup and usage instructions
- API documentation with examples
- Architecture decision records (ADRs)
- Contributing guidelines

#### Process Documentation
- Development workflows documented
- Onboarding guides for new developers
- Runbooks for common operations
- Incident response procedures

---

## Enforcement Mechanisms

### Automated Checks
- Pre-commit hooks for code formatting and linting
- CI pipeline runs all tests and quality checks
- Coverage gates prevent low-coverage merges
- Security scanning blocks vulnerable dependencies

### Code Review Process
- Mandatory peer review for all changes
- Review checklist includes TDD compliance
- Senior developer approval for architectural changes
- Security review for sensitive changes

### Quality Metrics
- Track test coverage trends
- Monitor code complexity metrics
- Measure defect escape rates
- Track mean time to recovery

---

## Consequences of Rule Violations

### First Offense
- Immediate feedback and education
- Required rework to comply with standards
- Additional code review requirements

### Repeated Offenses
- Temporary removal from main branch access
- Required pairing with senior developer
- Additional training assignments

### Critical Violations
- Security breaches or data loss
- Immediate rollback of changes
- Formal review process
- Possible disciplinary action

---

**Remember: These rules exist to ensure code quality, team productivity, and system reliability. They are guidelines for professional excellence, not restrictions on creativity.**
