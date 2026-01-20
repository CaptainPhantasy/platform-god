# PLATFORM GOD - Task Completion Checklist

When a coding task is completed, the following should be done:

## 1. Run Tests
```bash
pytest
```
All 284 tests should pass.

## 2. Format Code
```bash
ruff format src/ tests/
```

## 3. Run Linting
```bash
ruff check --fix src/ tests/
```

## 4. Type Check
```bash
mypy src/
```

## 5. Security Scan
```bash
bandit -r src/
```

## 6. Check Test Coverage
```bash
pytest --cov=src/platform_god --cov-report=html
```
Target: >80% coverage

## 7. Update Documentation
- If adding new agents, update agent documentation
- If changing API, update API documentation
- Update CHANGELOG.md for user-facing changes

## 8. Commit Changes
- Use descriptive commit messages
- Reference relevant issues if applicable
