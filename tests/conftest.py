"""Pytest configuration and fixtures."""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Disable authentication and rate limiting for tests
os.environ.setdefault("PG_REQUIRE_AUTH", "false")
os.environ.setdefault("PG_RATE_LIMIT", "1000/second")
os.environ.setdefault("PG_MAX_REQUEST_SIZE", "100M")


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_repo_dir(temp_dir: Path) -> Generator[Path, None, None]:
    """Provide a temporary repository directory with basic structure."""
    repo_dir = temp_dir / "test_repo"
    repo_dir.mkdir()

    # Create common directories
    (repo_dir / "src").mkdir()
    (repo_dir / "tests").mkdir()
    (repo_dir / "docs").mkdir()

    # Create sample files
    (repo_dir / "README.md").write_text("# Test Repository")
    (repo_dir / "src" / "main.py").write_text("print('hello')")
    (repo_dir / "tests" / "test_main.py").write_text("def test(): pass")

    return repo_dir


@pytest.fixture
def agents_dir() -> Path:
    """Return the path to the agents prompts directory."""
    here = Path(__file__).parent
    return here.parent / "prompts" / "agents"


@pytest.fixture
def mock_agent_content() -> str:
    """Provide mock agent prompt content for testing."""
    return """```text
You are PG_TEST_AGENT.

ROLE
Test agent for unit testing.

GOAL
Provide valid test output.

NON-GOALS (EXPLICIT)
- Do not modify any files
- Do not access external resources

SCOPE / PERMISSIONS (HARD)
Allowed:
- Read repository files and directories

Disallowed:
- Any writes
- Any network access

OPERATING RULES (MANDATORY)
1. Deterministic execution only.
2. No assumptions beyond provided input.

INPUT
- repository_root: string (absolute path to repository root)

PRECHECKS (MUST PASS BEFORE DOING ANY WORK)
- Verify repository_root exists

TASKS (EXECUTE IN ORDER — NO REORDERING)
A) Return success status

VALIDATION (MUST PASS AT THE END)
- Output is valid JSON

OUTPUT (STRICT — NO EXTRA TEXT)
Return ONLY JSON in this exact shape:
{
  "status": "success",
  "test_output": "test_value",
  "timestamp": "ISO8601 timestamp"
}

FAILURE HANDLING
If any step fails:
* STOP immediately
* Return failure output with error details

STOP CONDITIONS (HARD)
- repository_root does not exist
```
"""
