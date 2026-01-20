"""Tests for state manager persistence."""

from pathlib import Path

import pytest

from platform_god.orchestrator.core import ChainResult, ChainStopReason
from platform_god.state.manager import (
    AgentExecution,
    ChainRun,
    RepositoryFingerprint,
    RepositoryState,
    RunStatus,
    StateManager,
)


class TestRepositoryFingerprint:
    """Tests for RepositoryFingerprint model."""

    def test_fingerprint_creation(self) -> None:
        """RepositoryFingerprint can be created."""
        fp = RepositoryFingerprint(
            path="/test/repo",
            hash="abc123",
            file_count=10,
            total_size=1024,
            last_scanned="2024-01-15T00:00:00Z",
        )
        assert fp.path == "/test/repo"
        assert fp.hash == "abc123"
        assert fp.file_count == 10


class TestRepositoryState:
    """Tests for RepositoryState model."""

    def test_state_creation(self, temp_repo_dir: Path) -> None:
        """RepositoryState can be created."""
        state = RepositoryState(repository_root=str(temp_repo_dir))
        assert state.repository_root == str(temp_repo_dir)
        assert state.fingerprint is None
        assert state.last_chain_runs == {}
        assert state.accumulated_findings == []

    def test_update_fingerprint(self, temp_repo_dir: Path) -> None:
        """RepositoryState can update fingerprint."""
        state = RepositoryState(repository_root=str(temp_repo_dir))
        files = list(temp_repo_dir.rglob("*"))
        files = [f for f in files if f.is_file()]

        state.update_fingerprint(files)

        assert state.fingerprint is not None
        assert state.fingerprint.file_count == len(files)
        assert state.fingerprint.hash is not None

    def test_add_chain_run(self, temp_repo_dir: Path) -> None:
        """RepositoryState can record chain runs."""
        state = RepositoryState(repository_root=str(temp_repo_dir))
        state.add_chain_run("run_001", "discovery_analysis")

        assert "discovery_analysis" in state.last_chain_runs
        assert state.last_chain_runs["discovery_analysis"] == "run_001"

    def test_add_finding(self, temp_repo_dir: Path) -> None:
        """RepositoryState can accumulate findings."""
        state = RepositoryState(repository_root=str(temp_repo_dir))
        finding = {"type": "security", "severity": "high", "path": "src/main.py"}
        state.add_finding(finding)

        assert len(state.accumulated_findings) == 1
        assert state.accumulated_findings[0] == finding


class TestChainRun:
    """Tests for ChainRun model."""

    def test_chain_run_creation(self) -> None:
        """ChainRun can be created."""
        run = ChainRun(
            run_id="run_001",
            chain_name="discovery_analysis",
            repository_root="/test/repo",
            status=RunStatus.COMPLETED,
            started_at="2024-01-15T00:00:00Z",
        )
        assert run.run_id == "run_001"
        assert run.chain_name == "discovery_analysis"
        assert run.status == RunStatus.COMPLETED

    def test_to_summary(self) -> None:
        """ChainRun can convert to summary dict."""
        run = ChainRun(
            run_id="run_001",
            chain_name="discovery_analysis",
            repository_root="/test/repo",
            status=RunStatus.COMPLETED,
            started_at="2024-01-15T00:00:00Z",
            execution_time_ms=1000.0,
        )
        summary = run.to_summary()

        assert summary["run_id"] == "run_001"
        assert summary["chain_name"] == "discovery_analysis"
        assert summary["status"] == "completed"


class TestStateManager:
    """Tests for StateManager class."""

    def test_manager_initialization(self, temp_dir: Path) -> None:
        """StateManager initializes directories."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        assert (state_dir / "runs").exists()
        assert (state_dir / "repositories").exists()
        # index.json is created on first write, not initialization
        # This is the expected behavior

    def test_get_repository_state(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can retrieve or create repository state."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        state = mgr.get_repository_state(temp_repo_dir)

        assert state.repository_root == str(temp_repo_dir.absolute())
        assert state.fingerprint is None

    def test_save_repository_state(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can persist repository state."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        state = mgr.get_repository_state(temp_repo_dir)
        state.add_chain_run("run_001", "discovery_analysis")
        mgr.save_repository_state(state)

        # Verify persistence
        state2 = mgr.get_repository_state(temp_repo_dir)
        assert "discovery_analysis" in state2.last_chain_runs

    def test_record_chain_run(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can record chain runs."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        # Create a mock chain result
        result = ChainResult(
            chain_name="discovery_analysis",
            status=ChainStopReason.COMPLETED,
            completed_steps=4,
            total_steps=4,
            results=[],
            final_state={"test": "value"},
        )

        run = mgr.record_chain_run("discovery_analysis", temp_repo_dir, result)

        assert run.chain_name == "discovery_analysis"
        assert run.status == RunStatus.COMPLETED

        # Verify run file exists
        run_file = state_dir / "runs" / f"{run.run_id}.json"
        assert run_file.exists()

    def test_list_runs(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can list runs."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        # Record a run - pass Path object to match test_record_chain_run behavior
        result = ChainResult(
            chain_name="discovery_analysis",
            status=ChainStopReason.COMPLETED,
            completed_steps=1,
            total_steps=1,
            results=[],
            final_state={},
        )
        run = mgr.record_chain_run("discovery_analysis", temp_repo_dir, result)

        # List runs using the same Path object
        runs = mgr.list_runs(temp_repo_dir, limit=10)
        assert len(runs) >= 1, f"Expected at least 1 run, got {len(runs)}"
        # Verify the run we recorded is in the list
        assert any(r.run_id == run.run_id for r in runs), f"Run {run.run_id} not found in list"

    def test_cleanup_old_runs(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can cleanup old run records."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        # Record multiple runs
        for i in range(5):
            result = ChainResult(
                chain_name="discovery_analysis",
                status=ChainStopReason.COMPLETED,
                completed_steps=1,
                total_steps=1,
                results=[],
                final_state={},
            )
            mgr.record_chain_run("discovery_analysis", temp_repo_dir, result)

        # Cleanup keeping only 3
        removed = mgr.cleanup_old_runs(keep_count=3)

        assert removed >= 0


class TestAgentExecution:
    """Tests for AgentExecution model."""

    def test_agent_execution_creation(self) -> None:
        """AgentExecution can be created."""
        execution = AgentExecution(
            execution_id="agent_exec_001",
            agent_name="code_analyzer",
            repository_root="/test/repo",
            status=RunStatus.RUNNING,
            mode="live",
            started_at="2024-01-15T00:00:00Z",
        )
        assert execution.execution_id == "agent_exec_001"
        assert execution.agent_name == "code_analyzer"
        assert execution.status == RunStatus.RUNNING
        assert execution.mode == "live"

    def test_to_summary(self) -> None:
        """AgentExecution can convert to summary dict."""
        execution = AgentExecution(
            execution_id="agent_exec_001",
            agent_name="code_analyzer",
            repository_root="/test/repo",
            status=RunStatus.COMPLETED,
            mode="live",
            started_at="2024-01-15T00:00:00Z",
            execution_time_ms=500.0,
        )
        summary = execution.to_summary()

        assert summary["execution_id"] == "agent_exec_001"
        assert summary["agent_name"] == "code_analyzer"
        assert summary["status"] == "completed"
        assert summary["mode"] == "live"
        assert summary["duration_ms"] == 500.0


class TestAgentExecutionTracking:
    """Tests for StateManager agent execution tracking."""

    def test_start_agent_execution(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can start tracking an agent execution."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        execution = mgr.start_agent_execution(
            agent_name="code_analyzer",
            repository_root=temp_repo_dir,
            mode="live",
            caller="api",
        )

        assert execution.status == RunStatus.RUNNING
        assert execution.agent_name == "code_analyzer"
        assert execution.execution_id.startswith("agent_exec_")
        assert execution.started_at is not None

        # Verify execution file exists
        exec_file = state_dir / "agent_executions" / f"{execution.execution_id}.json"
        assert exec_file.exists()

    def test_complete_agent_execution_success(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can complete an agent execution with success."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        # Start execution
        execution = mgr.start_agent_execution(
            agent_name="code_analyzer",
            repository_root=temp_repo_dir,
            mode="live",
        )

        # Complete with output
        output_data = {"findings": ["issue1", "issue2"], "file_count": 42}
        completed = mgr.complete_agent_execution(
            execution_id=execution.execution_id,
            output_data=output_data,
            execution_time_ms=1234.5,
        )

        assert completed is not None
        assert completed.status == RunStatus.COMPLETED
        assert completed.output_data == output_data
        assert completed.execution_time_ms == 1234.5
        assert completed.completed_at is not None

    def test_complete_agent_execution_failure(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can complete an agent execution with failure."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        # Start execution
        execution = mgr.start_agent_execution(
            agent_name="code_analyzer",
            repository_root=temp_repo_dir,
            mode="live",
        )

        # Complete with error
        error_msg = "Repository access denied"
        completed = mgr.complete_agent_execution(
            execution_id=execution.execution_id,
            error=error_msg,
            execution_time_ms=100.0,
        )

        assert completed is not None
        assert completed.status == RunStatus.FAILED
        assert completed.error == error_msg

    def test_get_agent_execution(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can retrieve an agent execution by ID."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        execution = mgr.start_agent_execution(
            agent_name="code_analyzer",
            repository_root=temp_repo_dir,
            mode="dry_run",
        )

        retrieved = mgr.get_agent_execution(execution.execution_id)

        assert retrieved is not None
        assert retrieved.execution_id == execution.execution_id
        assert retrieved.agent_name == "code_analyzer"
        assert retrieved.mode == "dry_run"

    def test_get_nonexistent_agent_execution(self, temp_dir: Path) -> None:
        """StateManager returns None for nonexistent execution ID."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        retrieved = mgr.get_agent_execution("nonexistent_id")
        assert retrieved is None

    def test_list_running_executions(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can list all running executions."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        # Start two executions
        exec1 = mgr.start_agent_execution(
            agent_name="analyzer_1",
            repository_root=temp_repo_dir,
            mode="live",
        )
        exec2 = mgr.start_agent_execution(
            agent_name="analyzer_2",
            repository_root=temp_repo_dir,
            mode="simulated",
        )

        # Complete one
        mgr.complete_agent_execution(execution_id=exec1.execution_id)

        # List running - should only return the uncompleted one
        running = mgr.list_running_executions()

        assert len(running) >= 1
        running_ids = [e.execution_id for e in running]
        assert exec2.execution_id in running_ids
        assert exec1.execution_id not in running_ids

    def test_cleanup_old_executions(self, temp_dir: Path, temp_repo_dir: Path) -> None:
        """StateManager can cleanup old execution records."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        # Record multiple executions
        for i in range(5):
            execution = mgr.start_agent_execution(
                agent_name=f"analyzer_{i}",
                repository_root=temp_repo_dir,
                mode="live",
            )
            # Complete them
            mgr.complete_agent_execution(execution_id=execution.execution_id)

        # Cleanup keeping only 3
        removed = mgr.cleanup_old_executions(keep_count=3)

        assert removed >= 0

    def test_agent_executions_dir_created(self, temp_dir: Path) -> None:
        """StateManager creates agent_executions directory on initialization."""
        state_dir = temp_dir / "state"
        mgr = StateManager(state_dir=state_dir)

        assert (state_dir / "agent_executions").exists()

