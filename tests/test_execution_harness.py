"""Tests for execution harness (with mocked LLM)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from platform_god.agents.executor import (
    ExecutionContext,
    ExecutionHarness,
    ExecutionMode,
)
from platform_god.agents.registry import get_global_registry
from platform_god.core.exceptions import AgentNotFoundError
from platform_god.core.models import AgentClass, AgentStatus


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_all_modes_defined(self) -> None:
        """All expected execution modes are defined."""
        expected = {"dry_run", "simulated", "live"}
        actual = {em.value for em in ExecutionMode}
        assert actual == expected


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    def test_default_context(self, temp_repo_dir: Path) -> None:
        """ExecutionContext can be created with defaults."""
        ctx = ExecutionContext(
            repository_root=temp_repo_dir,
            agent_name="PG_DISCOVERY",
        )
        assert ctx.repository_root == temp_repo_dir
        assert ctx.agent_name == "PG_DISCOVERY"
        assert ctx.mode == ExecutionMode.DRY_RUN
        assert ctx.caller == "system"

    def test_context_with_mode(self, temp_repo_dir: Path) -> None:
        """ExecutionContext can specify execution mode."""
        ctx = ExecutionContext(
            repository_root=temp_repo_dir,
            agent_name="PG_DISCOVERY",
            mode=ExecutionMode.LIVE,
        )
        assert ctx.mode == ExecutionMode.LIVE


class TestExecutionHarness:
    """Tests for ExecutionHarness class."""

    def test_harness_initialization(self, temp_dir: Path) -> None:
        """ExecutionHarness initializes with audit directory."""
        audit_dir = temp_dir / "audit"
        harness = ExecutionHarness(audit_dir=audit_dir)
        assert audit_dir.exists()

    def test_execute_nonexistent_agent(self, temp_repo_dir: Path) -> None:
        """Executing non-existent agent raises AgentNotFoundError."""
        harness = ExecutionHarness()
        ctx = ExecutionContext(
            repository_root=temp_repo_dir,
            agent_name="PG_NONEXISTENT",
        )

        with pytest.raises(AgentNotFoundError, match="not found in registry"):
            harness.execute("PG_NONEXISTENT", {}, ctx)

    def test_execute_dry_run(self, temp_repo_dir: Path) -> None:
        """Dry run mode returns mock output without LLM call."""
        registry = get_global_registry()
        agent = registry.get("PG_DISCOVERY")
        if agent is None:
            pytest.skip("PG_DISCOVERY agent not found")

        harness = ExecutionHarness()
        ctx = ExecutionContext(
            repository_root=temp_repo_dir,
            agent_name="PG_DISCOVERY",
            mode=ExecutionMode.DRY_RUN,
        )

        result = harness.execute("PG_DISCOVERY", {"repository_root": str(temp_repo_dir)}, ctx)

        assert result.status == AgentStatus.COMPLETED
        assert result.output_data is not None
        assert result.output_data.get("mode") == "dry_run"

    def test_execute_simulated(self, temp_repo_dir: Path) -> None:
        """Simulated mode returns schema-based mock output."""
        registry = get_global_registry()
        agent = registry.get("PG_DISCOVERY")
        if agent is None:
            pytest.skip("PG_DISCOVERY agent not found")

        harness = ExecutionHarness()
        ctx = ExecutionContext(
            repository_root=temp_repo_dir,
            agent_name="PG_DISCOVERY",
            mode=ExecutionMode.SIMULATED,
        )

        result = harness.execute("PG_DISCOVERY", {"repository_root": str(temp_repo_dir)}, ctx)

        assert result.status == AgentStatus.COMPLETED
        assert result.output_data is not None
        assert result.output_data.get("mode") == "simulated"

    def test_execute_invalid_repo_path(self, temp_dir: Path) -> None:
        """Execution fails when repository root does not exist."""
        harness = ExecutionHarness()
        nonexistent = temp_dir / "nonexistent_repo"

        ctx = ExecutionContext(
            repository_root=nonexistent,
            agent_name="PG_DISCOVERY",
        )

        result = harness.execute("PG_DISCOVERY", {}, ctx)

        assert result.status == AgentStatus.STOPPED
        assert "repository_root does not exist" in result.error_message

    @patch("platform_god.llm.client.LLMClient")
    def test_execute_live_mocked(self, mock_llm_client: MagicMock, temp_repo_dir: Path) -> None:
        """Live mode with mocked LLM client returns expected result."""
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = '{"status": "success", "test": "value"}'
        mock_response.parse_json.return_value = {"status": "success", "test": "value"}
        mock_response.model = "claude-3-5-sonnet-20241022"
        mock_response.provider.value = "anthropic"
        mock_response.tokens_used = 100

        mock_client_instance = MagicMock()
        mock_client_instance.complete.return_value = mock_response
        mock_llm_client.return_value = mock_client_instance

        registry = get_global_registry()
        agent = registry.get("PG_DISCOVERY")
        if agent is None:
            pytest.skip("PG_DISCOVERY agent not found")

        harness = ExecutionHarness()
        ctx = ExecutionContext(
            repository_root=temp_repo_dir,
            agent_name="PG_DISCOVERY",
            mode=ExecutionMode.LIVE,
        )

        result = harness.execute("PG_DISCOVERY", {"repository_root": str(temp_repo_dir)}, ctx)

        assert result.status == AgentStatus.COMPLETED
        assert result.output_data is not None

    def test_audit_log_written(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """Execution writes audit log entry."""
        audit_dir = temp_dir / "audit"
        harness = ExecutionHarness(audit_dir=audit_dir)

        ctx = ExecutionContext(
            repository_root=temp_repo_dir,
            agent_name="PG_DISCOVERY",
            mode=ExecutionMode.DRY_RUN,
        )

        harness.execute("PG_DISCOVERY", {"repository_root": str(temp_repo_dir)}, ctx)

        # Check audit log was created
        log_files = list(audit_dir.glob("execution_*.jsonl"))
        assert len(log_files) > 0

        # Verify log entry
        log_content = log_files[0].read_text()
        assert "PG_DISCOVERY" in log_content
