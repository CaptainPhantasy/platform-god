"""Tests for core data models."""

import json

from pydantic import ValidationError

from platform_god.core.models import (
    AgentClass,
    AgentInput,
    AgentOutput,
    AgentPermissions,
    AgentResult,
    AgentStatus,
    GuardrailDecision,
    GuardrailRequest,
    VerificationRequest,
    VerificationResult,
    WriteDecision,
    WriteRequest,
)


class TestAgentClass:
    """Tests for AgentClass enum."""

    def test_all_agent_classes_defined(self) -> None:
        """Verify all expected agent classes are defined."""
        expected_classes = {
            "READ_ONLY_SCAN",
            "PLANNING_SYNTHESIS",
            "REGISTRY_STATE",
            "WRITE_GATED",
            "CONTROL_PLANE",
        }
        actual_classes = {ac.value for ac in AgentClass}
        assert actual_classes == expected_classes


class TestAgentPermissions:
    """Tests for AgentPermissions dataclass."""

    def test_default_permissions(self) -> None:
        """Default permissions allow read, no write or network."""
        perms = AgentPermissions()
        assert perms.can_read is True
        assert perms.can_write is False
        assert perms.can_network is False
        assert perms.allowed_write_paths == ()
        assert perms.disallowed_paths == ()

    def test_read_only_scan_permissions(self) -> None:
        """READ_ONLY_SCAN class has no write or network access."""
        perms = AgentPermissions.for_class(AgentClass.READ_ONLY_SCAN)
        assert perms.can_read is True
        assert perms.can_write is False
        assert perms.can_network is False

    def test_registry_state_permissions(self) -> None:
        """REGISTRY_STATE can write to var/registry/ and var/audit/."""
        perms = AgentPermissions.for_class(AgentClass.REGISTRY_STATE)
        assert perms.can_read is True
        assert perms.can_write is True
        assert perms.can_network is False
        assert "var/registry/" in perms.allowed_write_paths
        assert "var/audit/" in perms.allowed_write_paths

    def test_write_gated_permissions(self) -> None:
        """WRITE_GATED has specific allowed and disallowed paths."""
        perms = AgentPermissions.for_class(AgentClass.WRITE_GATED)
        assert perms.can_read is True
        assert perms.can_write is True
        assert perms.can_network is False
        assert "prompts/agents/" in perms.allowed_write_paths
        assert "var/artifacts/" in perms.allowed_write_paths
        assert "src/" in perms.disallowed_paths
        assert "tests/" in perms.disallowed_paths

    def test_control_plane_permissions(self) -> None:
        """CONTROL_PLANE has broad write access."""
        perms = AgentPermissions.for_class(AgentClass.CONTROL_PLANE)
        assert perms.can_read is True
        assert perms.can_write is True
        assert perms.can_network is False
        assert "var/" in perms.allowed_write_paths
        assert perms.disallowed_paths == ()


class TestAgentInput:
    """Tests for AgentInput model."""

    def test_minimal_input(self, temp_repo_dir: Path) -> None:
        """AgentInput can be created with just repository_root."""
        inp = AgentInput(repository_root=temp_repo_dir)
        assert inp.repository_root == temp_repo_dir
        assert inp.parameters == {}

    def test_input_with_parameters(self, temp_repo_dir: Path) -> None:
        """AgentInput accepts additional parameters."""
        inp = AgentInput(
            repository_root=temp_repo_dir,
            parameters={"key": "value", "number": 42}
        )
        assert inp.parameters["key"] == "value"
        assert inp.parameters["number"] == 42

    def test_input_accepts_extra_fields(self, temp_repo_dir: Path) -> None:
        """AgentInput allows extra fields via model config."""
        inp = AgentInput(
            repository_root=temp_repo_dir,
            custom_field="custom_value"
        )
        assert inp.model_dump()["custom_field"] == "custom_value"


class TestAgentOutput:
    """Tests for AgentOutput model."""

    def test_success_output(self) -> None:
        """AgentOutput can represent success."""
        out = AgentOutput(status="success", data={"result": "value"})
        assert out.status == "success"
        assert out.data["result"] == "value"
        assert out.error is None

    def test_failure_output(self) -> None:
        """AgentOutput can represent failure."""
        out = AgentOutput(status="failure", error="Something went wrong")
        assert out.status == "failure"
        assert out.error == "Something went wrong"

    def test_timestamp_auto_generated(self) -> None:
        """AgentOutput generates timestamp automatically."""
        out = AgentOutput(status="success")
        assert out.timestamp is not None
        assert "T" in out.timestamp  # ISO format


class TestAgentResult:
    """Tests for AgentResult model."""

    def test_success_result(self) -> None:
        """AgentResult can represent successful execution."""
        result = AgentResult(
            agent_name="PG_TEST",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.COMPLETED,
            input_data={"key": "value"},
            output_data={"result": "success"},
            execution_time_ms=100.0,
        )
        assert result.agent_name == "PG_TEST"
        assert result.agent_class == AgentClass.READ_ONLY_SCAN
        assert result.status == AgentStatus.COMPLETED
        assert result.is_success() is True

    def test_failure_result(self) -> None:
        """AgentResult can represent failed execution."""
        result = AgentResult(
            agent_name="PG_TEST",
            agent_class=AgentClass.READ_ONLY_SCAN,
            status=AgentStatus.FAILED,
            input_data={},
            error_message="Execution failed",
        )
        assert result.status == AgentStatus.FAILED
        assert result.is_success() is False


class TestWriteRequest:
    """Tests for WriteRequest model."""

    def test_create_request(self) -> None:
        """WriteRequest can be created for create operation."""
        req = WriteRequest(
            operation="create",
            target_path="var/artifacts/test.json",
            content='{"key": "value"}',
            actor="system",
        )
        assert req.operation == "create"
        assert req.target_path == "var/artifacts/test.json"


class TestWriteDecision:
    """Tests for WriteDecision model."""

    def test_allow_decision(self) -> None:
        """WriteDecision can represent an allow decision."""
        dec = WriteDecision(
            decision="allow",
            operation="create",
            target_path="var/artifacts/test.json",
            actor="PG_DOC_MANAGER",
            reasoning="Path is within allowed write paths",
        )
        assert dec.decision == "allow"

    def test_deny_decision(self) -> None:
        """WriteDecision can represent a deny decision."""
        dec = WriteDecision(
            decision="deny",
            operation="create",
            target_path="src/main.py",
            actor="PG_DOC_MANAGER",
            violated_rule_id="SRC_WRITE_PROHIBITED",
            reasoning="src/ is in disallowed paths",
        )
        assert dec.decision == "deny"
        assert dec.violated_rule_id == "SRC_WRITE_PROHIBITED"


class TestGuardrailRequest:
    """Tests for GuardrailRequest model."""

    def test_guardrail_request(self) -> None:
        """GuardrailRequest can be created."""
        req = GuardrailRequest(
            operation_type="write",
            target_path="var/test.json",
            operation_context={"agent": "PG_TEST"},
        )
        assert req.operation_type == "write"
        assert req.target_path == "var/test.json"


class TestGuardrailDecision:
    """Tests for GuardrailDecision model."""

    def test_guardrail_allow(self) -> None:
        """GuardrailDecision can allow an operation."""
        dec = GuardrailDecision(
            decision="allow",
            explanation="Operation passes all guardrails"
        )
        assert dec.decision == "allow"
        assert dec.violated_rule_id is None


class TestVerificationRequest:
    """Tests for VerificationRequest model."""

    def test_verification_request(self) -> None:
        """VerificationRequest can be created."""
        req = VerificationRequest(
            work_description="Update documentation",
            acceptance_criteria=["All docs updated", "No broken links"],
            deliverable_paths=["docs/README.md"],
        )
        assert req.work_description == "Update documentation"
        assert len(req.acceptance_criteria) == 2


class TestVerificationResult:
    """Tests for VerificationResult model."""

    def test_pass_verification(self) -> None:
        """VerificationResult can represent passed verification."""
        result = VerificationResult(
            result="pass",
            work_description="Update documentation",
            criteria_evaluations=[
                {"criteria": "All docs updated", "passed": True},
                {"criteria": "No broken links", "passed": True},
            ],
            summary={"total": 2, "passed": 2, "failed": 0},
        )
        assert result.result == "pass"
        assert result.summary["passed"] == 2

    def test_fail_verification(self) -> None:
        """VerificationResult can represent failed verification."""
        result = VerificationResult(
            result="fail",
            work_description="Update documentation",
            criteria_evaluations=[
                {"criteria": "All docs updated", "passed": True},
                {"criteria": "No broken links", "passed": False},
            ],
            failed_criteria=["No broken links"],
            summary={"total": 2, "passed": 1, "failed": 1},
        )
        assert result.result == "fail"
        assert "No broken links" in result.failed_criteria
