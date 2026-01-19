# Test-Driven Development (TDD) Rules

## The Golden Rule ⚡

**NEVER write production code without first writing a failing test.**

This is not optional. This is not "when you have time". This is ALWAYS.

## TDD Workflow

### 1. Red Phase - Write a Failing Test
```python
# ALWAYS start here
def test_prompt_version_creation():
    # Test that doesn't work yet
    prompt = PromptService.create_version(...)
    assert prompt.version_number == 1  # This will fail
```

### 2. Green Phase - Make It Pass
```python
# Now write the minimal code to pass
def create_version(...):
    # Simple implementation that makes test pass
    return Prompt(version_number=1, ...)
```

### 3. Refactor Phase - Improve
```python
# Now clean up and optimize
def create_version(...):
    # Better implementation with proper logic
    return calculate_next_version(...)
```

## Mandatory TDD Practices

### For Every New Feature
1. **Write the acceptance test first** - What should this feature do?
2. **Write integration tests** - How do components work together?
3. **Write unit tests** - How does each piece work individually?
4. **Watch tests fail** - Confirm they fail for the right reasons
5. **Implement code** - Write minimal code to pass tests
6. **Refactor** - Improve while keeping tests green

### For Every Bug Fix
1. **Write a test that reproduces the bug** - Make it fail
2. **Fix the bug** - Make the test pass
3. **Add regression tests** - Ensure this never happens again

### For Every Enhancement
1. **Write tests for new behavior**
2. **Ensure existing tests still pass**
3. **Refactor if needed**

## Test Types & Requirements

### 1. Unit Tests (Most Common)
- Test individual functions and methods
- Fast, isolated, no external dependencies
- Mock external services (database, APIs, etc.)
- 100% coverage of business logic

### 2. Integration Tests
- Test component interactions
- Database integration with test database
- API endpoint testing
- Service layer interactions

### 3. End-to-End Tests
- Complete user workflows
- Real external services (when possible)
- Performance and load testing
- Security testing

## Test Organization

### File Structure
```
tests/
├── unit/
│   ├── test_models.py
│   ├── test_services.py
│   └── test_utils.py
├── integration/
│   ├── test_api.py
│   ├── test_database.py
│   └── test_workers.py
├── e2e/
│   ├── test_workflows.py
│   └── test_performance.py
└── fixtures/
    ├── __init__.py
    └── data.py
```

### Test Naming Convention
```python
# Good: Descriptive, explains the scenario
def test_prompt_version_incremented_when_content_changes():
    pass

def test_execution_fails_when_template_has_undefined_variables():
    pass

def test_async_execution_queues_task_and_returns_id():
    pass

# Bad: Vague, doesn't explain what's being tested
def test_prompt():
    pass

def test_execution():
    pass
```

### Test Structure (AAA Pattern)
```python
def test_prompt_version_creation_with_checksum():
    # Arrange - Set up the test
    template_source = "Hello {{name}}"
    expected_checksum = compute_checksum(template_source)
    
    # Act - Execute the code being tested
    version = PromptVersion.create(template_source)
    
    # Assert - Verify the results
    assert version.checksum_hash == expected_checksum
    assert version.version_number == 1
```

## TDD Anti-Patterns (DO NOT DO)

### ❌ The "I'll write tests later" approach
```python
# WRONG: Writing code first
def calculate_version():
    # Complex logic here
    return version

# "I'll test this tomorrow" (means never)
```

### ❌ The "Tests are too hard" excuse
```python
# WRONG: Skipping tests because they're difficult
def complex_api_integration():
    # "This is too hard to test, I'll skip it"
    pass
```

### ❌ The "Just test the happy path" mistake
```python
# WRONG: Only testing success cases
def test_prompt_creation():
    prompt = create_prompt("test")
    assert prompt.name == "test"
    # Missing: error cases, edge cases, validation
```

### ❌ The "Mock everything" overkill
```python
# WRONG: Mocking too much, testing nothing
def test_service():
    mock_db = Mock()
    mock_api = Mock()
    mock_logger = Mock()
    # What are we actually testing?
```

## TDD Best Practices

### 1. Test First, Always
- No exceptions, no excuses
- Even for "simple" changes
- Even for "quick fixes"

### 2. Keep Tests Small and Focused
- One assertion per test when possible
- Test one behavior at a time
- Use descriptive test names

### 3. Use Test Doubles Appropriately
- Mock external dependencies
- Use factories for test data
- Don't mock the system under test

### 4. Maintain Test Quality
- Tests should be readable and maintainable
- Remove duplication in tests
- Keep test data simple and focused

### 5. Run Tests Frequently
- Run tests after every small change
- Use watch mode during development
- Fix failing tests immediately

## Code Review Checklist for TDD Compliance

### Before Approving Any PR:
- [ ] Are there failing tests for the new feature?
- [ ] Do all tests pass (including new ones)?
- [ ] Is test coverage adequate?
- [ ] Are tests testing the right things?
- [ ] Are test names descriptive?
- [ ] Are tests well-structured and readable?

### Red Flags to Watch For:
- PR with "tests coming later"
- Low test coverage on new code
- Tests that are too complex or brittle
- Missing edge case and error testing
- Tests that don't actually test anything meaningful

## TDD Tools & Setup

### Required Tools
```bash
# Testing framework
pytest

# Test utilities
pytest-asyncio  # For async tests
pytest-cov      # Coverage reporting
pytest-mock     # Mocking utilities
factory-boy     # Test data factories

# Test database
pytest-postgresql  # Test database setup
```

### Pre-commit Configuration
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
        args: [tests/]
```

## TDD in Our Workflow

### Daily Development
1. Pick a task/story
2. Write failing test(s)
3. Implement code to pass
4. Refactor while green
5. Repeat until feature complete
6. Run full test suite
7. Commit and push

### Pull Request Process
1. All tests must pass
2. New code must have tests
3. Coverage must not decrease
4. Code review checks TDD compliance
5. Merge only when all checks pass

### Emergency Fixes
1. Write test reproducing the issue
2. Fix the issue
3. Ensure all tests pass
4. Add regression tests
5. Deploy fix

---

## Remember: TDD is not about testing. It's about design.

Writing tests first forces you to think about:
- What should this code do?
- How should it behave?
- What are the edge cases?
- How will components interact?

This leads to better design, fewer bugs, and more maintainable code.

**TDD is mandatory. There are no exceptions.**
