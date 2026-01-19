# Development Rules & Guidelines

This directory contains the comprehensive development rules and guidelines for the Prompt Ledger project. All team members must read, understand, and follow these rules.

## 📋 Rule Documents

### Core Rules (Mandatory)
- **[development.md](./development.md)** - Complete development standards and practices
- **[tdd.md](./tdd.md)** - Test-Driven Development rules (NON-NEGOTIABLE)
- **[git-workflow.md](./git-workflow.md)** - Git branching and commit standards
- **[code-review.md](./code-review.md)** - Code review process and guidelines

## 🚨 Critical Rules

### 1. Test-Driven Development (TDD) - ABSOLUTE MANDATORY
- **NEVER** write production code without first writing failing tests
- **ALWAYS** follow Red-Green-Refactor cycle
- **NO EXCEPTIONS** - This rule applies to every single change

### 2. Code Quality Standards
- 90%+ test coverage required
- All code must pass automated quality checks
- Documentation required for all public APIs

### 3. Git & Collaboration
- Conventional commit format required
- All PRs require code review approval
- Main branch must always be deployable

## 📊 Enforcement

### Automated Checks
- Pre-commit hooks for formatting and linting
- CI pipeline runs all tests and quality gates
- Coverage gates prevent low-coverage merges
- Security scanning blocks vulnerable code

### Manual Enforcement
- Code review checklist includes TDD compliance
- Senior developer approval for architectural changes
- Regular audits of rule compliance

### Consequences
- First offense: Education and rework required
- Repeated offenses: Temporary loss of merge privileges
- Critical violations: Formal review process

## 🎯 Getting Started

1. **Read all rule documents** before writing any code
2. **Set up development environment** with all required tools
3. **Run the test suite** to ensure everything works
4. **Start with a small feature** to practice the workflow
5. **Ask questions** if anything is unclear

## 🔧 Tools Required

```bash
# Install development dependencies
pip install -e ".[dev]"

# Set up pre-commit hooks
pre-commit install

# Verify setup
pytest tests/
black --check src/
isort --check-only src/
flake8 src/
mypy src/
```

## 📚 Learning Resources

### Test-Driven Development
- [Test-Driven Development by Example](https://www.amazon.com/Test-Driven-Development-Kent-Beck/dp/0321146530)
- [Growing Object-Oriented Software, Guided by Tests](https://www.amazon.com/Growing-Object-Oriented-Software-Guided-Tests/dp/0321503627)

### Clean Code Practices
- [Clean Code by Robert C. Martin](https://www.amazon.com/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350884)
- [The Clean Coder](https://www.amazon.com/Clean-Coder-Professional-Programmers-Development/dp/0137081073)

### Git Best Practices
- [Pro Git Book](https://git-scm.com/book/en/v2)
- [GitHub Flow](https://guides.github.com/introduction/flow/)

## 🤝 Contributing to Rules

These rules are living documents. To suggest improvements:

1. **Create an issue** describing the proposed change
2. **Discuss with the team** in meetings or PR comments
3. **Submit a PR** with the rule changes
4. **Get team approval** before merging
5. **Communicate changes** to all team members

## ❓ Questions & Support

If you have questions about these rules:

1. **Check this README** and the relevant rule document
2. **Search existing issues** for similar questions
3. **Ask in team channels** (Slack, Teams, etc.)
4. **Schedule a discussion** with a senior developer
5. **Document the answer** for future reference

---

## 🎉 Remember: These rules exist to help us succeed

They ensure:
- ✅ High-quality, maintainable code
- ✅ Fewer bugs and regressions
- ✅ Better team collaboration
- ✅ Faster development velocity
- ✅ Professional growth for everyone

**Following these rules makes us a better, more effective team.**
