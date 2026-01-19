# Git Workflow Rules

## Branch Strategy

### Main Branches
- `main`: Production-ready code, always deployable
- `develop`: Integration branch for features (if using GitFlow)

### Feature Branches
```bash
# Naming convention
feature/prompt-versioning
feature/async-execution
feature/openai-provider

# Bug fixes
fix/auth-validation
fix/memory-leak
fix/api-timeout

# Hotfixes (from main)
hotfix/security-patch
hotfix/critical-bug-fix
```

### Branch Rules
- **Never commit directly to main** (except hotfixes)
- **Feature branches from main** (latest approach) or develop
- **Keep branches focused** on single features/fixes
- **Regular merges** to avoid large divergences
- **Delete merged branches** to keep repository clean

## Commit Standards

### Conventional Commit Format
```bash
type(scope): description

feat(api): add prompt versioning endpoint
fix(worker): handle async task timeouts
docs(readme): update installation instructions
test(models): add prompt version tests
refactor(db): optimize query performance
style(api): fix code formatting
chore(deps): update openai dependency
```

### Commit Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code formatting (no logic changes)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes
- `build`: Build system changes

### Commit Message Rules
- **Present tense**: "add feature" not "added feature"
- **Lowercase**: Always lowercase after type
- **No period**: Don't end description with period
- **Descriptive**: Explain what and why, not how
- **Issue references**: Include ticket numbers when applicable

### Examples
```bash
# Good
feat(api): add prompt versioning with checksum validation
fix(worker): retry failed async tasks with exponential backoff
test(execution): add integration tests for sync/async modes

# Bad
added new stuff
fix bug
update files
```

## Pull Request Process

### PR Requirements
- **All tests must pass**
- **Code coverage must not decrease**
- **Documentation updated** (if applicable)
- **Tests included for new code**
- **Code review approved** by at least one team member
- **CI/CD pipeline successful**

### PR Template
```markdown
## Description
Brief description of changes and why they're needed.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing
- [ ] Manual testing completed
- [ ] Test coverage adequate

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] No breaking changes (or documented)

## Issue References
Closes #123
Related to #456
```

### Review Process
1. **Developer creates PR** with proper template
2. **Automated checks run** (tests, linting, security)
3. **Code review** by team members
4. **Address feedback** and update as needed
5. **Approval** and merge to main

## Code Review Guidelines

### Review Checklist
- **Functionality**: Does the code work as intended?
- **Testing**: Are tests comprehensive and appropriate?
- **Design**: Is the code well-designed and maintainable?
- **Performance**: Are there performance concerns?
- **Security**: Are there security vulnerabilities?
- **Documentation**: Is code properly documented?
- **Style**: Does code follow project standards?

### Review Etiquette
- **Be constructive** and helpful
- **Explain reasoning** for suggested changes
- **Ask questions** instead of making demands
- **Acknowledge good work** and improvements
- **Focus on code, not person**

## Git Configuration

### Required Setup
```bash
# User configuration
git config --global user.name "Your Name"
git config --global user.email "your.email@company.com"

# Default branch name
git config --global init.defaultBranch main

# Pull strategy
git config --global pull.rebase false

# Push strategy
git config --global push.default simple
```

### Hooks Setup
```bash
# Pre-commit hook (runs before each commit)
#!/bin/sh
pytest tests/
black --check src/ tests/
isort --check-only src/ tests/
flake8 src/ tests/

# Pre-push hook (runs before each push)
#!/bin/sh
pytest tests/ --cov=src/
mypy src/
```

## Advanced Git Practices

### Rebase vs Merge
```bash
# Use rebase for feature branches (clean history)
git checkout feature-branch
git fetch origin
git rebase origin/main

# Use merge for main branch (preserve history)
git checkout main
git merge feature-branch
```

### Interactive Rebase
```bash
# Clean up commit history before merging
git rebase -i HEAD~5

# Commands:
# pick = use commit
# reword = use commit, but edit message
# edit = use commit, but stop for amending
# squash = use commit, but meld into previous commit
# fixup = like squash, but discard this commit's message
```

### Conflict Resolution
```bash
# When conflicts occur:
git status                    # See what's conflicted
# Edit files to resolve conflicts
git add resolved files        # Mark as resolved
git commit                   # Complete merge/rebase
```

## Repository Management

### Tagging
```bash
# Create version tag
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push tags
git push origin v1.0.0
git push origin --tags
```

### Release Branches
```bash
# Create release branch
git checkout -b release/v1.1.0 main

# After release, merge back
git checkout main
git merge release/v1.1.0
git tag v1.1.0
```

### Hotfix Process
```bash
# Create hotfix from main
git checkout -b hotfix/critical-bug main

# Fix and test
# ... make changes ...

# Merge back to main
git checkout main
git merge hotfix/critical-bug
git tag v1.1.1
```

## Git Hygiene

### Regular Maintenance
```bash
# Clean up merged branches
git branch -d feature-branch
git push origin --delete feature-branch

# Clean up stale remote branches
git remote prune origin

# Check repository size
git count-objects -vH
```

### Large Files Handling
```bash
# Use Git LFS for large files
git lfs track "*.zip"
git lfs track "*.pdf"
git add .gitattributes
```

### Security Practices
```bash
# Never commit:
# - API keys, passwords, secrets
# - Large binary files
# - Personal data
# - Temporary files

# Use .gitignore properly
echo "*.pyc" >> .gitignore
echo ".env" >> .gitignore
echo "__pycache__/" >> .gitignore
```

## Troubleshooting

### Common Issues
```bash
# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Fix committed message
git commit --amend -m "New message"

# Stash changes temporarily
git stash
git stash pop

# Recover lost commit
git reflog
git checkout <commit-hash>
```

### Emergency Procedures
```bash
# If main is broken:
git checkout main
git reset --hard <last-good-commit>
git push --force-with-lease origin main

# Always communicate with team before force pushing!
```

---

## Remember: Git is a collaboration tool.

Clean history, clear commits, and proper branching make the entire team more effective.
