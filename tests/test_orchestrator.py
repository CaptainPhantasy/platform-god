"""Tests for orchestrator core module."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from platform_god.agents.executor import ExecutionContext, ExecutionHarness, ExecutionMode
from platform_god.agents.registry import get_global_registry
from platform_god.core.models import AgentClass, AgentResult, AgentStatus
from platform_god.orchestrator.core import (
    AgentStep,
    ChainDefinition,
    ChainResult,
    ChainState,
    ChainStopReason,
    Orchestrator,
)


class TestChainStopReason:
    """Tests for ChainStopReason enum."""

    def test_all_reasons_defined(self) -> None:
        """All expected stop reasons are defined."""
        expected = {
            "completed",
            "agent_failed",
            "precheck_failed",
            "stop_condition",
            "manual",
        }
        actual = {csr.value for csr in ChainStopReason}
        assert actual == expected


class TestAgentStep:
    """Tests for AgentStep dataclass."""

    def test_minimal_step(self) -> None:
        """AgentStep can be created with minimal parameters."""
        step = AgentStep(agent_name="PG_DISCOVERY")
        assert step.agent_name == "PG_DISCOVERY"
        assert step.input_mapping is None
        assert step.output_key is None
        assert step.continue_on_failure is False

    def test_step_with_all_fields(self) -> None:
        """AgentStep can have all fields specified."""
        step = AgentStep(
            agent_name="PG_DISCOVERY",
            input_mapping="$.previous",
            output_key="discovery",
            continue_on_failure=True,
        )
        assert step.agent_name == "PG_DISCOVERY"
        assert step.input_mapping == "$.previous"
        assert step.output_key == "discovery"
        assert step.continue_on_failure is True


class TestChainDefinition:
    """Tests for ChainDefinition class."""

    def test_discovery_chain(self) -> None:
        """Discovery chain has correct steps."""
        chain = ChainDefinition.discovery_chain()
        assert chain.name == "discovery_analysis"
        assert len(chain.steps) == 4
        assert chain.steps[0].agent_name == "PG_DISCOVERY"
        assert chain.steps[1].agent_name == "PG_STACKMAP"
        assert chain.steps[2].agent_name == "PG_HEALTH_SCORE"
        assert chain.steps[3].agent_name == "PG_REPORT_WRITER"

    def test_security_scan_chain(self) -> None:
        """Security scan chain has correct steps."""
        chain = ChainDefinition.security_scan_chain()
        assert chain.name == "security_scan"
        assert len(chain.steps) == 3
        assert chain.steps[0].agent_name == "PG_DISCOVERY"
        assert chain.steps[1].agent_name == "PG_SECRETS_AND_RISK"

    def test_dependency_audit_chain(self) -> None:
        """Dependency audit chain has correct steps."""
        chain = ChainDefinition.dependency_audit_chain()
        assert chain.name == "dependency_audit"
        assert len(chain.steps) == 4

    def test_doc_generation_chain(self) -> None:
        """Doc generation chain has correct steps."""
        chain = ChainDefinition.doc_generation_chain()
        assert chain.name == "doc_generation"
        assert len(chain.steps) == 5

    def test_tech_debt_chain(self) -> None:
        """Tech debt chain has correct steps."""
        chain = ChainDefinition.tech_debt_chain()
        assert chain.name == "tech_debt"
        assert len(chain.steps) == 5

    def test_full_analysis_chain(self) -> None:
        """Full analysis chain has all steps."""
        chain = ChainDefinition.full_analysis_chain()
        assert chain.name == "full_analysis"
        assert len(chain.steps) == 8

    def test_custom_chain(self) -> None:
        """Custom chain can be created."""
        chain = ChainDefinition(
            name="custom",
            description="A custom chain",
            steps=[
                AgentStep(agent_name="PG_DISCOVERY"),
                AgentStep(agent_name="PG_REPORT_WRITER"),
            ],
        )
        assert chain.name == "custom"
        assert len(chain.steps) == 2


class TestChainResult:
    """Tests for ChainResult dataclass."""

    def test_completed_result(self) -> None:
        """ChainResult can represent completed chain."""
        result = ChainResult(
            chain_name="test_chain",
            status=ChainStopReason.COMPLETED,
            completed_steps=3,
            total_steps=3,
            results=[],
            final_state={"key": "value"},
        )
        assert result.chain_name == "test_chain"
        assert result.status == ChainStopReason.COMPLETED
        assert result.completed_steps == 3

    def test_failed_result(self) -> None:
        """ChainResult can represent failed chain."""
        result = ChainResult(
            chain_name="test_chain",
            status=ChainStopReason.AGENT_FAILED,
            completed_steps=1,
            total_steps=3,
            results=[],
            error="Agent failed",
        )
        assert result.status == ChainStopReason.AGENT_FAILED
        assert result.error == "Agent failed"


class TestChainState:
    """Tests for ChainState class."""

    def test_initial_state(self) -> None:
        """ChainState starts with empty data."""
        state = ChainState()
        assert state.data == {}
        assert state.step_index == 0

    def test_set_and_get_output(self) -> None:
        """ChainState can store and retrieve output."""
        state = ChainState()
        state.set_output("test_key", {"result": "value"})
        assert state.get_output("test_key") == {"result": "value"}

    def test_get_nonexistent_key(self) -> None:
        """ChainState returns None for nonexistent key."""
        state = ChainState()
        assert state.get_output("nonexistent") is None

    def test_resolve_input_null_mapping(self, temp_repo_dir: Path) -> None:
        """Null input mapping returns initial state."""
        state = ChainState()
        initial = {"repository_root": str(temp_repo_dir)}
        result = state.resolve_input(None, initial)
        assert result == initial
        assert result is not initial  # Should be a copy

    def test_resolve_input_single_key(self) -> None:
        """Single key extraction from state."""
        state = ChainState()
        state.data["discovery"] = {"files": ["a.py"]}
        result = state.resolve_input("$.discovery", {})
        assert result == {"discovery": {"files": ["a.py"]}}

    def test_resolve_input_multiple_keys(self) -> None:
        """Multiple key extraction from state."""
        state = ChainState()
        state.data["discovery"] = {"files": ["a.py"]}
        state.data["health"] = {"score": 85}
        result = state.resolve_input("$.discovery,$.health", {})
        assert "discovery" in result
        assert "health" in result

    def test_resolve_input_from_initial_state(self) -> None:
        """Keys can be extracted from initial state."""
        state = ChainState()
        initial = {"repository_root": "/test"}
        result = state.resolve_input("$.repository_root", initial)
        assert result == {"repository_root": "/test"}

    def test_resolve_input_fallback_to_initial(self) -> None:
        """Falls back to initial state if key not in current data."""
        state = ChainState()
        state.data["other"] = "value"
        initial = {"repository_root": "/test", "other": "ignored"}
        result = state.resolve_input("$.repository_root", initial)
        assert result == {"repository_root": "/test"}

    def test_step_index_incremented(self) -> None:
        """Step index can be set and retrieved."""
        state = ChainState()
        state.step_index = 5
        assert state.step_index == 5


class TestOrchestrator:
    """Tests for Orchestrator class."""

    def test_orchestrator_initialization(self) -> None:
        """Orchestrator initializes with default harness and registry."""
        orchestrator = Orchestrator()
        assert orchestrator._harness is not None
        assert orchestrator._registry is not None

    def test_orchestrator_with_custom_harness(self) -> None:
        """Orchestrator can accept custom harness."""
        custom_harness = ExecutionHarness()
        orchestrator = Orchestrator(harness=custom_harness)
        assert orchestrator._harness is custom_harness

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_execute_chain_single_step(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Execute single-step chain."""
        # Mock the harness
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness
        mock_result = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={"status": "success"},
            execution_time_ms=100.0,
        )
        mock_harness.execute.return_value = mock_result

        chain = ChainDefinition(
            name="test_chain",
            description="Test chain",
            steps=[AgentStep(agent_name="PG_DISCOVERY", output_key="result")],
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(chain, temp_repo_dir, ExecutionMode.DRY_RUN)

        assert result.chain_name == "test_chain"
        assert result.status == ChainStopReason.COMPLETED
        assert result.completed_steps == 1
        assert result.total_steps == 1
        assert len(result.results) == 1

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_execute_chain_multiple_steps(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Execute multi-step chain with state passing."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        def mock_execute(agent_name: str, input_data: dict, context: ExecutionContext) -> AgentResult:
            return AgentResult(
                agent_name=agent_name,
                agent_class=AgentClass.READ_ONLY_SCAN,
                status=AgentStatus.COMPLETED,
                input_data=input_data,
                output_data={"agent": agent_name, "data": input_data.get("key", "default")},
            )

        mock_harness.execute.side_effect = mock_execute

        chain = ChainDefinition(
            name="test_chain",
            description="Test chain",
            steps=[
                AgentStep(agent_name="PG_DISCOVERY", output_key="step1"),
                AgentStep(agent_name="PG_STACKMAP", input_mapping="$.step1", output_key="step2"),
            ],
            initial_state={"key": "value"},
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(chain, temp_repo_dir, ExecutionMode.DRY_RUN)

        assert result.completed_steps == 2
        assert result.status == ChainStopReason.COMPLETED
        assert mock_harness.execute.call_count == 2

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_execute_chain_stops_on_failure(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Chain stops when agent fails."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        # First step succeeds, second fails
        mock_harness.execute.side_effect = [
            AgentResult(
                agent_name="PG_DISCOVERY",
                agent_class=AgentClass.READ_ONLY_SCAN,
                status=AgentStatus.COMPLETED,
                input_data={},
                output_data={"status": "success"},
            ),
            AgentResult(
                agent_name="PG_STACKMAP",
                agent_class=AgentClass.READ_ONLY_SCAN,
                status=AgentStatus.FAILED,
                input_data={},
                error_message="Agent failed",
            ),
        ]

        chain = ChainDefinition(
            name="test_chain",
            description="Test chain",
            steps=[
                AgentStep(agent_name="PG_DISCOVERY"),
                AgentStep(agent_name="PG_STACKMAP"),
                AgentStep(agent_name="PG_HEALTH_SCORE"),  # Should not execute
            ],
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(chain, temp_repo_dir, ExecutionMode.DRY_RUN)

        assert result.status == ChainStopReason.AGENT_FAILED
        assert result.completed_steps == 2
        assert result.total_steps == 3
        assert mock_harness.execute.call_count == 2

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_execute_chain_continues_on_failure(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Chain continues when continue_on_failure is True."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        mock_harness.execute.side_effect = [
            AgentResult(
                agent_name="PG_DISCOVERY",
                agent_class=AgentClass.READ_ONLY_SCAN,
                status=AgentStatus.COMPLETED,
                input_data={},
                output_data={"status": "success"},
            ),
            AgentResult(
                agent_name="PG_STACKMAP",
                agent_class=AgentClass.READ_ONLY_SCAN,
                status=AgentStatus.FAILED,
                input_data={},
                error_message="Agent failed",
            ),
            AgentResult(
                agent_name="PG_HEALTH_SCORE",
                agent_class=AgentClass.READ_ONLY_SCAN,
                status=AgentStatus.COMPLETED,
                input_data={},
                output_data={"status": "success"},
            ),
        ]

        chain = ChainDefinition(
            name="test_chain",
            description="Test chain",
            steps=[
                AgentStep(agent_name="PG_DISCOVERY"),
                AgentStep(agent_name="PG_STACKMAP", continue_on_failure=True),
                AgentStep(agent_name="PG_HEALTH_SCORE"),
            ],
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(chain, temp_repo_dir, ExecutionMode.DRY_RUN)

        assert result.status == ChainStopReason.COMPLETED
        assert result.completed_steps == 3
        assert mock_harness.execute.call_count == 3

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_execute_chain_with_callback(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Callback is invoked after each step."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        callback_calls = []

        def mock_callback(result: AgentResult) -> None:
            callback_calls.append(result.agent_name)

        mock_harness.execute.return_value = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={},
        )

        chain = ChainDefinition(
            name="test_chain",
            description="Test chain",
            steps=[
                AgentStep(agent_name="PG_DISCOVERY"),
                AgentStep(agent_name="PG_STACKMAP"),
            ],
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(
            chain, temp_repo_dir, ExecutionMode.DRY_RUN, on_step_complete=mock_callback
        )

        assert len(callback_calls) == 2

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_execute_discovery_chain(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Execute discovery chain convenience method."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        mock_harness.execute.return_value = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={},
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_discovery_chain(temp_repo_dir)

        assert result.chain_name == "discovery_analysis"

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_execute_security_chain(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Execute security chain convenience method."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        mock_harness.execute.return_value = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={},
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_security_chain(temp_repo_dir)

        assert result.chain_name == "security_scan"

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_chain_summary(self, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Chain summary generates human-readable output."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        mock_harness.execute.return_value = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={},
            execution_time_ms=150.5,
        )

        chain = ChainDefinition(
            name="test_chain",
            description="Test",
            steps=[AgentStep(agent_name="PG_DISCOVERY")],
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(chain, temp_repo_dir)
        summary = orchestrator.chain_summary(result)

        assert "Chain: test_chain" in summary
        assert "Status: completed" in summary
        assert "Steps: 1/1" in summary
        assert "✓" in summary
        assert "150ms" in summary

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_persist_chain_result(self, mock_harness_class: MagicMock, temp_dir: Path, temp_repo_dir: Path) -> None:
        """Chain result can be persisted to disk."""
        output_dir = temp_dir / "output"
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        mock_harness.execute.return_value = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={"result": "data"},
            timestamp="2024-01-15T12:00:00Z",
        )

        chain = ChainDefinition(
            name="test_chain",
            description="Test",
            steps=[AgentStep(agent_name="PG_DISCOVERY")],
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(chain, temp_repo_dir)
        output_path = orchestrator.persist_chain_result(result, output_dir)

        assert output_path.exists()
        content = output_path.read_text()
        assert "test_chain" in content

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    def test_persist_chain_result_empty_results(self, mock_harness_class: MagicMock, temp_dir: Path, temp_repo_dir: Path) -> None:
        """Chain result with no results uses 'unknown' timestamp."""
        output_dir = temp_dir / "output"
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness

        chain = ChainDefinition(
            name="test_chain",
            description="Test",
            steps=[],
        )

        orchestrator = Orchestrator()
        result = ChainResult(
            chain_name="test_chain",
            status=ChainStopReason.COMPLETED,
            completed_steps=0,
            total_steps=0,
            results=[],
        )
        output_path = orchestrator.persist_chain_result(result, output_dir)

        assert output_path.exists()
        assert "unknown" in output_path.name

    @patch("platform_god.orchestrator.core.ExecutionHarness")
    @patch("platform_god.state.manager.StateManager")
    def test_record_chain_run(self, mock_state_mgr_class: MagicMock, mock_harness_class: MagicMock, temp_repo_dir: Path) -> None:
        """Chain run is recorded in state manager."""
        mock_harness = MagicMock()
        mock_harness_class.return_value = mock_harness
        mock_state_mgr = MagicMock()
        mock_state_mgr_class.return_value = mock_state_mgr

        mock_harness.execute.return_value = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={},
        )

        mock_chain_run = MagicMock()
        mock_chain_run.run_id = "test_run_id"
        mock_state_mgr.record_chain_run.return_value = mock_chain_run

        chain = ChainDefinition(
            name="test_chain",
            description="Test",
            steps=[AgentStep(agent_name="PG_DISCOVERY")],
        )

        orchestrator = Orchestrator()
        result = orchestrator.execute_chain(chain, temp_repo_dir)
        chain_run = orchestrator.record_chain_run(result, temp_repo_dir)

        mock_state_mgr.record_chain_run.assert_called_once()
