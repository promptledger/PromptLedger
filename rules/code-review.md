# Code Review Guidelines

## Review Philosophy

Code review is about:
- **Quality assurance** - catching bugs and issues
- **Knowledge sharing** - learning from each other
- **Team alignment** - maintaining consistent standards
- **Mentorship** - helping developers grow

Be constructive, respectful, and focused on improving the codebase.

## Review Process

### 1. Pre-Review Checklist
Before submitting code for review:
- [ ] Code follows all style guidelines
- [ ] All tests pass locally
- [ ] New code has corresponding tests
- [ ] Documentation is updated
- [ ] Self-review completed
- [ ] No TODO/FIXME comments left in code

### 2. Automated Checks
All PRs must pass:
- **Unit tests** (100% pass rate)
- **Integration tests** (100% pass rate)
- **Code coverage** (no decrease from baseline)
- **Static analysis** (flake8, mypy, security scan)
- **Code formatting** (black, isort)

### 3. Human Review Process
1. **Functionality Review**
   - Does the code solve the intended problem?
   - Are there edge cases not handled?
   - Is the logic correct and efficient?

2. **Design Review**
   - Is the code well-structured?
   - Does it follow architectural patterns?
   - Is it maintainable and extensible?

3. **Testing Review**
   - Are tests comprehensive?
   - Do tests cover edge cases?
   - Are tests well-written and maintainable?

4. **Security Review**
   - Are there security vulnerabilities?
   - Is input validation proper?
   - Are secrets handled correctly?

## Review Criteria

### Must-Have (Blockers)
- **Tests fail** or missing tests for new code
- **Security vulnerabilities**
- **Breaking changes** without documentation
- **Performance regressions**
- **Code doesn't work** as intended
- **Violates TDD principles**

### Should-Have (Strong Suggestions)
- **Code style violations**
- **Poor error handling**
- **Missing documentation**
- **Unclear or complex code**
- **Inefficient implementations**
- **Inconsistent patterns**

### Nice-to-Have (Suggestions)
- **Minor optimizations**
- **Alternative approaches**
- **Additional test cases**
- **Documentation improvements**
- **Code organization suggestions**

## Review Guidelines by Area

### API Design
```python
# Good: Clear, consistent, well-documented
@router.post("/prompts/{name}/versions", response_model=PromptVersionResponse)
async def create_prompt_version(
    name: str,
    version_data: PromptVersionCreate,
    db: AsyncSession = Depends(get_db),
) -> PromptVersionResponse:
    """Create a new version of an existing prompt.
    
    Args:
        name: Name of the prompt to version
        version_data: Version configuration
        db: Database session
        
    Returns:
        Created prompt version details
        
    Raises:
        HTTPException: If prompt not found or validation fails
    """
```

### Database Operations
```python
# Good: Proper async handling, error management
async def get_active_version(
    db: AsyncSession, prompt_id: UUID
) -> Optional[PromptVersion]:
    """Get the active version for a prompt."""
    try:
        result = await db.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_id == prompt_id,
                PromptVersion.status == "active",
            )
        )
        return result.scalar_one_or_none()
    except DatabaseError as e:
        logger.error(f"Database error getting active version: {e}")
        raise
```

### Error Handling
```python
# Good: Specific exceptions, proper logging
async def render_template(template: str, variables: dict) -> str:
    """Render template with variables."""
    try:
        env = Environment(undefined=StrictUndefined)
        jinja_template = env.from_string(template)
        return jinja_template.render(**variables)
    except TemplateError as e:
        logger.warning(f"Template rendering failed: {e}")
        raise ValidationError(f"Invalid template: {e}")
    except UndefinedError as e:
        logger.error(f"Undefined variable in template: {e}")
        raise ValidationError(f"Missing variable: {e}")
```

### Testing
```python
# Good: Clear test structure, comprehensive coverage
class TestPromptVersioning:
    """Test prompt versioning functionality."""
    
    async def test_version_incremented_on_content_change(
        self, db_session, sample_prompt
    ):
        """Test that version number increments when content changes."""
        # Arrange
        original_version = sample_prompt.active_version.version_number
        
        # Act
        new_version = await create_prompt_version(
            db_session, sample_prompt.name, "New content"
        )
        
        # Assert
        assert new_version.version_number == original_version + 1
        assert new_version.checksum_hash != sample_prompt.active_version.checksum_hash
```

## Review Comment Guidelines

### Comment Types
1. **Issues** - Must be fixed
2. **Suggestions** - Consider changing
3. **Questions** - Need clarification
4. **Praise** - Acknowledge good work

### Comment Format
```markdown
# Issue (must fix)
**Issue:** The error handling here is too broad and will catch DatabaseError.
**Suggestion:** Catch specific exceptions and handle them appropriately.
**Example:**
```python
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise
```

# Question (need clarification)
**Question:** Why are we using a synchronous database operation here? Should this be async?

# Suggestion (consider changing)
**Suggestion:** Consider using a dataclass for the response to make it more type-safe.

# Praise (acknowledge good work)
**Great work!** The test coverage here is excellent and the error handling is robust.
```

### Review Etiquette

### Do ✅
- Be specific and constructive
- Explain the reasoning behind suggestions
- Provide examples of improvements
- Acknowledge good practices and effort
- Ask questions to understand intent
- Focus on the code, not the person

### Don't ❌
- Use vague or dismissive language
- Make personal criticisms
- Suggest changes without explanation
- Overlook good work in favor of criticism
- Use absolute terms ("always", "never")
- Rush through reviews without careful consideration

## Special Review Areas

### Security Review Checklist
- [ ] Input validation and sanitization
- [ ] Authentication and authorization
- [ ] SQL injection prevention
- [ ] XSS prevention
- [ ] Secret management
- [ ] Dependency security
- [ ] Error message information disclosure

### Performance Review Checklist
- [ ] Database query optimization
- [ ] Proper indexing
- [ ] Memory usage efficiency
- [ ] Async/await usage
- [ ] Caching strategies
- [ ] External API call efficiency
- [ ] Algorithm complexity

### Testing Review Checklist
- [ ] Test coverage adequacy
- [ ] Test quality and maintainability
- [ ] Edge case coverage
- [ ] Error condition testing
- [ ] Integration test completeness
- [ ] Test data management
- [ ] Mock usage appropriateness

## Review Tools and Automation

### Required Tools
```yaml
# .github/workflows/review.yml
name: Code Review Checks
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: pytest --cov=src
      - name: Code quality
        run: |
          black --check src/
          isort --check-only src/
          flake8 src/
          mypy src/
      - name: Security scan
        run: bandit -r src/
```

### Review Assistant Tools
- **GitHub CodeQL** - Security vulnerability scanning
- **SonarCloud** - Code quality analysis
- **CodeClimate** - Test coverage and quality
- **LGTM.com** - Automated code review

## Review Metrics

### Track These Metrics
- **Review turnaround time** - How quickly reviews happen
- **Review participation** - Who is reviewing code
- ** defect density** - Bugs found per review
- **Review coverage** - Percentage of code reviewed
- **Rejection rate** - PRs that need major changes

### Quality Indicators
- **Few bugs in production** - Reviews are catching issues
- **Consistent code style** - Reviews maintain standards
- **Good test coverage** - Reviews enforce testing
- **Fast onboarding** - New developers learn from reviews

## Escalation Process

### When Disagreements Occur
1. **Discuss** in PR comments
2. **Pair program** to explore alternatives
3. **Involve tech lead** for architectural decisions
4. **Team discussion** for significant changes
5. **Document decision** in ADR (Architecture Decision Record)

### Emergency Reviews
- **Critical bugs** - Immediate review by senior dev
- **Security issues** - Security team review required
- **Production outages** - Rapid review process
- **Customer escalations** - Priority review

---

## Remember: Code review is a conversation, not a judgment.

The goal is to improve the codebase and help each other grow as developers. Be kind, be thorough, and be constructive.
