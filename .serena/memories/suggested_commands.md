# PLATFORM GOD - Suggested Commands

## Development Commands

### Installation
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install
pip install -e .
```

### Testing
```bash
# Run all tests (284 tests)
pytest

# Run with coverage
pytest --cov=src/platform_god --cov-report=html

# Run specific test file
pytest tests/test_api_integration.py
```

### Code Quality
```bash
# Format code
ruff format src/ tests/

# Fix linting issues
ruff check --fix src/ tests/

# Run linting
ruff check src/ tests/

# Type checking
mypy src/

# Security scanning
bandit -r src/
```

### CLI Usage
```bash
# List all agents
pgod agents list

# List all chains
pgod chains list

# Run a chain (dry-run)
pgod run discovery /path/to/repo --dry-run

# Run with output
pgod run security_scan /path/to/repo --output report.json

# View run history
pgod history

# Inspect a repository
pgod inspect /path/to/repo

# Start the API server
pgod serve
```

### Build
```bash
# Build distribution
python -m build
```

## System Commands (Darwin/macOS)

- `ls` - List directory contents
- `cd` - Change directory
- `pwd` - Print working directory
- `grep` - Search text
- `find` - Find files
- `cat` - View file contents
- `head`/`tail` - View file portions
- `open` - Open files (macOS specific)
