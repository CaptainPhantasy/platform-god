# Contributing to Platform God

Thank you for your interest in contributing to Platform God!

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@example.com.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- A GitHub account

### Development Setup

```bash
# 1. Fork the repository on GitHub
# 2. Clone your fork
git clone https://github.com/your-username/platform-god.git
cd platform-god

# 3. Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 4. Install with dev dependencies
pip install -e ".[dev]"

# 5. Install additional development tools
pip install ruff mypy bandit yamllint

# 6. Run tests to verify setup
pytest

# 7. Create a branch for your work
git checkout -b feature/your-feature-name
```

## Making Changes

### What to Work On

Check the [Issues](https://github.com/platform-god-project/platform-god/issues) for open items, especially those labeled `good first issue` or `help wanted`.

#### Priority Areas

1. **Security** (HIGH)
   - Enable auth enforcement by default
   - Add rate limiting

2. **Test Coverage** (MEDIUM)
   - Add tests for uncovered modules (artifacts/, audit/, automations/, notifications/)
   - Increase overall coverage from 28%

3. **Code Quality** (MEDIUM)
   - Fix 153 ruff errors (mostly unused imports)
   - Resolve 91 mypy type errors

4. **Documentation** (LOW)
   - Complete empty docstrings
   - Add usage examples

### Coding Standards

#### Python Style

- Follow [PEP 8](https://peps8.org/)
- Use [ruff](https://docs.astral.sh/ruff/) for linting
- Use type hints (enforced by mypy)
- Maximum line length: 100 characters

#### Formatting

```bash
# Format code
ruff format src/ tests/

# Fix linting issues
ruff check --fix src/ tests/
```

#### Type Checking

```bash
# Run type checker
mypy src/
```

#### Security

```bash
# Run security linter
bandit -r src/
```

## Testing

### Run All Tests

```bash
pytest
```

### Run with Coverage

```bash
pytest --cov=src/platform_god --cov-report=html --cov-report=term
```

### Run Specific Tests

```bash
# Test file
pytest tests/test_api_integration.py

# Specific test
pytest tests/test_api_integration.py::TestAgentsEndpoints::test_list_agents

# With verbose output
pytest -v tests/test_cli.py
```

### Test Requirements

- All tests must pass before submitting a PR
- New features require tests
- Bug fixes require tests that prevent regression
- Maintain or improve test coverage

## Submitting Changes

### Commit Messages

Follow conventional commit format:

```
<type>[optional scope]: <description>

[optional body]

[optional footer]
```

**Types:** feat, fix, docs, style, refactor, test, chore

**Examples:**

```
feat(agents): add new security scanning agent

Fixes #123
```

```
fix(api): resolve auth middleware not enforcing by default

Security fix - set require_auth=True by default
```

### Pull Request Process

1. Update the CHANGELOG.md with your changes
2. Ensure all tests pass
3. Ensure code passes linting (`ruff check`, `mypy`, `bandit`)
4. Update documentation if needed
5. Push to your fork and submit a pull request

### PR Description Template

```markdown
## Summary
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests added/updated
- [ ] All tests pass

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] No new warnings generated
```

## Project Structure

When adding new code, follow the existing structure:

```
src/platform_god/
├── agents/          # Agent definitions and execution
├── api/             # REST API
├── core/            # Data models and exceptions
├── llm/             # LLM client
├── orchestrator/    # Chain orchestration
├── state/           # State management
└── registry/        # Entity storage
```

## Adding a New Agent

1. Create agent prompt in `prompts/agents/YOUR_AGENT.md`
2. Follow the agent template structure
3. Add to registry (auto-loaded on startup)
4. Add tests in `tests/test_agent_registry.py`
5. Update documentation

## Adding a New Chain

1. Define chain in `src/platform_god/api/routes/chains.py`
2. Add tests in `tests/test_orchestrator.py`
3. Update README with chain description

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions
- Check existing documentation first

---

**Thank you for contributing!**
