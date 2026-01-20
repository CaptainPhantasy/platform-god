"""
State Manager - persistent cross-run state storage.

Stores:
- Chain execution history
- Agent outputs
- Repository fingerprints
- Cross-run state for incremental analysis
"""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from platform_god.orchestrator.core import ChainResult


class RunStatus(Enum):
    """Status of a chain run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RepositoryFingerprint(BaseModel):
    """Fingerprint of a repository for change detection."""

    path: str
    hash: str
    file_count: int
    total_size: int
    last_scanned: str
    file_hashes: dict[str, str] = Field(default_factory=dict)
    git_commit_sha: str | None = Field(default=None, description="Git HEAD commit SHA if available")
    critical_files_hash: str | None = Field(default=None, description="Combined SHA256 of critical config files")


class ChainRun(BaseModel):
    """Record of a chain execution."""

    run_id: str
    chain_name: str
    repository_root: str
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    execution_time_ms: float | None = None
    agent_results: list[dict[str, Any]] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    def to_summary(self) -> dict[str, Any]:
        """Convert to summary for listing."""
        return {
            "run_id": self.run_id,
            "chain_name": self.chain_name,
            "repository": Path(self.repository_root).name,
            "status": self.status.value,
            "started_at": self.started_at,
            "duration_ms": self.execution_time_ms,
        }


class AgentExecution(BaseModel):
    """Record of a single agent execution via API."""

    execution_id: str
    agent_name: str
    repository_root: str
    status: RunStatus
    mode: str
    started_at: str
    completed_at: str | None = None
    execution_time_ms: float | None = None
    output_data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    caller: str = "api"

    def to_summary(self) -> dict[str, Any]:
        """Convert to summary for listing."""
        return {
            "execution_id": self.execution_id,
            "agent_name": self.agent_name,
            "repository": Path(self.repository_root).name,
            "status": self.status.value,
            "mode": self.mode,
            "started_at": self.started_at,
            "duration_ms": self.execution_time_ms,
        }


class RepositoryState(BaseModel):
    """Accumulated state for a repository across runs."""

    repository_root: str
    fingerprint: RepositoryFingerprint | None = None
    last_chain_runs: dict[str, str] = Field(
        default_factory=dict, description="chain_name -> run_id"
    )
    accumulated_findings: list[dict[str, Any]] = Field(
        default_factory=list, description="Findings from all runs"
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict, description="Accumulated metrics"
    )
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def _get_git_commit_sha(self) -> str | None:
        """Get the current git commit SHA if available."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repository_root,
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return None

    def _compute_file_content_hash(self, file_path: Path) -> str | None:
        """Compute SHA256 hash of file contents."""
        try:
            content = file_path.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except (OSError, PermissionError):
            return None

    def _get_critical_files(self) -> list[Path]:
        """Get list of critical config files to hash by content."""
        repo_path = Path(self.repository_root)
        critical_patterns = [
            "*.json",
            "*.yaml",
            "*.yml",
            "*.toml",
            "*.xml",
            "*.cfg",
            "*.ini",
            "*.lock",
            "Makefile",
            "Dockerfile*",
            "docker-compose*",
            ".gitignore",
            ".env*",
            "*.md",
            "requirements*.txt",
            "setup.py",
            "setup.cfg",
            "pyproject.toml",
            "package.json",
            "tsconfig.json",
        ]

        critical_files = []
        for pattern in critical_patterns:
            matches = list(repo_path.rglob(pattern))
            for m in matches:
                if m.is_file() and ".git" not in m.parts and "__pycache__" not in m.parts:
                    critical_files.append(m)

        # Also include common build/config dirs
        critical_dirs = [".github", "config", "configs"]
        for dir_name in critical_dirs:
            dir_path = repo_path / dir_name
            if dir_path.is_dir():
                critical_files.extend(dir_path.rglob("*"))

        # Dedupe while preserving order
        seen = set()
        unique_files = []
        for f in critical_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)

        return unique_files

    def update_fingerprint(self, files: list[Path]) -> None:
        """Update repository fingerprint with content-based hashing."""
        file_hashes = {}
        total_size = 0

        # Get git commit SHA for git repositories
        git_commit_sha = self._get_git_commit_sha()

        # Compute content hashes for critical files
        critical_files = self._get_critical_files()
        critical_hashes = []
        for file_path in critical_files:
            if file_path.is_file():
                content_hash = self._compute_file_content_hash(file_path)
                if content_hash:
                    relative_path = str(file_path.relative_to(self.repository_root))
                    critical_hashes.append(f"{relative_path}:{content_hash}")

        # Combine critical file hashes into single digest
        critical_files_hash = None
        if critical_hashes:
            combined = ":".join(sorted(critical_hashes))
            critical_files_hash = hashlib.sha256(combined.encode()).hexdigest()[:32]

        # Quick hash for all files (for backward compatibility and non-critical tracking)
        for file_path in files:
            if file_path.is_file():
                stat = file_path.stat()
                total_size += stat.st_size
                # Use SHA256 for the quick hash
                hash_input = f"{file_path}:{stat.st_size}:{stat.st_mtime}"
                file_hashes[str(file_path.relative_to(self.repository_root))] = hashlib.sha256(
                    hash_input.encode()
                ).hexdigest()[:8]

        # Compute overall repo hash - incorporate git SHA, critical files, and file hashes
        hash_components = [
            f"{len(files)}",
            f"{total_size}",
            f"{git_commit_sha or 'no-git'}",
            f"{critical_files_hash or 'no-critical'}",
        ]
        hash_components.extend(sorted(file_hashes.values()))
        repo_hash_input = ":".join(hash_components)
        repo_hash = hashlib.sha256(repo_hash_input.encode()).hexdigest()[:16]

        self.fingerprint = RepositoryFingerprint(
            path=self.repository_root,
            hash=repo_hash,
            file_count=len(files),
            total_size=total_size,
            last_scanned=datetime.now(timezone.utc).isoformat(),
            file_hashes=file_hashes,
            git_commit_sha=git_commit_sha,
            critical_files_hash=critical_files_hash,
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_chain_run(self, run_id: str, chain_name: str) -> None:
        """Record a chain run for this repository."""
        self.last_chain_runs[chain_name] = run_id
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_finding(self, finding: dict[str, Any]) -> None:
        """Add a finding from an analysis."""
        self.accumulated_findings.append(finding)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        """Update accumulated metrics."""
        self.metrics.update(metrics)
        self.updated_at = datetime.now(timezone.utc).isoformat()


class StateManager:
    """
    Manager for persistent state storage.

    State is stored in var/state/:
    - runs/<run_id>.json - Individual chain runs
    - repositories/<repo_hash>.json - Repository state
    - index.json - Global index
    """

    def __init__(self, state_dir: Path | None = None):
        """Initialize state manager with storage directory."""
        self._state_dir = state_dir or Path("var/state")
        self._runs_dir = self._state_dir / "runs"
        self._repos_dir = self._state_dir / "repositories"
        self._agent_executions_dir = self._state_dir / "agent_executions"
        self._index_file = self._state_dir / "index.json"

        for dir_path in (self._runs_dir, self._repos_dir, self._agent_executions_dir):
            dir_path.mkdir(parents=True, exist_ok=True)

        self._index = self._load_index()

    def _load_index(self) -> dict[str, Any]:
        """Load global index."""
        if self._index_file.exists():
            try:
                return json.loads(self._index_file.read_text())
            except json.JSONDecodeError:
                pass
        return {"runs": [], "repositories": []}

    def _save_index(self) -> None:
        """Save global index."""
        self._index_file.write_text(json.dumps(self._index, indent=2))

    def _get_repo_hash(self, repository_root: Path) -> str:
        """Get hash identifier for a repository."""
        return hashlib.sha256(str(repository_root).encode()).hexdigest()[:12]

    def _get_run_id(self) -> str:
        """Generate a unique run ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"run_{timestamp}"

    def _get_execution_id(self) -> str:
        """Generate a unique agent execution ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        return f"agent_exec_{timestamp}"

    def get_repository_state(self, repository_root: Path) -> RepositoryState:
        """Get or create repository state."""
        repo_hash = self._get_repo_hash(repository_root)
        repo_file = self._repos_dir / f"{repo_hash}.json"

        if repo_file.exists():
            try:
                data = json.loads(repo_file.read_text())
                return RepositoryState(**data)
            except (json.JSONDecodeError, ValueError):
                pass

        return RepositoryState(repository_root=str(repository_root.absolute()))

    def save_repository_state(self, state: RepositoryState) -> None:
        """Save repository state."""
        repo_hash = self._get_repo_hash(Path(state.repository_root))
        repo_file = self._repos_dir / f"{repo_hash}.json"

        repo_file.write_text(state.model_dump_json(indent=2))

        # Update index
        if repo_hash not in self._index.get("repositories", []):
            self._index.setdefault("repositories", []).append(repo_hash)
        self._save_index()

    def record_chain_run(
        self,
        chain_name: str,
        repository_root: Path,
        result: ChainResult | None = None,
    ) -> ChainRun:
        """
        Record a chain execution.

        Creates a ChainRun record, saves it, and updates repository state.
        """
        run_id = self._get_run_id()

        started_at = datetime.now(timezone.utc).isoformat()
        status = RunStatus.COMPLETED if result and result.status.value == "completed" else RunStatus.FAILED

        chain_run = ChainRun(
            run_id=run_id,
            chain_name=chain_name,
            repository_root=str(repository_root.absolute()),
            status=status,
            started_at=started_at,
        )

        if result:
            chain_run.completed_at = started_at  # Same time for now
            chain_run.execution_time_ms = sum(
                r.execution_time_ms or 0 for r in result.results
            )
            chain_run.agent_results = [
                {
                    "agent_name": r.agent_name,
                    "status": r.status.value,
                    "execution_time_ms": r.execution_time_ms,
                    "error": r.error_message,
                }
                for r in result.results
            ]
            chain_run.final_state = result.final_state
            chain_run.error = result.error

        # Save run record
        run_file = self._runs_dir / f"{run_id}.json"
        run_file.write_text(chain_run.model_dump_json(indent=2))

        # Update repository state
        repo_state = self.get_repository_state(repository_root)
        repo_state.add_chain_run(run_id, chain_name)
        self.save_repository_state(repo_state)

        # Update index
        self._index.setdefault("runs", []).insert(0, run_id)
        if len(self._index["runs"]) > 1000:  # Keep last 1000 runs
            self._index["runs"] = self._index["runs"][:1000]
        self._save_index()

        return chain_run

    def get_chain_run(self, run_id: str) -> ChainRun | None:
        """Get a chain run by ID."""
        run_file = self._runs_dir / f"{run_id}.json"
        if run_file.exists():
            try:
                data = json.loads(run_file.read_text())
                return ChainRun(**data)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def list_runs(
        self, repository_root: Path | None = None, limit: int = 50
    ) -> list[ChainRun]:
        """List recent chain runs, optionally filtered by repository."""
        run_ids = self._index.get("runs", [])[:limit]
        runs = []

        # Resolve repository_root to absolute path for consistent comparison
        resolved_root = None
        if repository_root is not None:
            resolved_root = str(repository_root.resolve())

        for run_id in run_ids:
            run = self.get_chain_run(run_id)
            if run:
                if resolved_root is None or run.repository_root == resolved_root:
                    runs.append(run)

        return runs

    def get_last_run(
        self, repository_root: Path, chain_name: str | None = None
    ) -> ChainRun | None:
        """Get the last run for a repository, optionally filtered by chain."""
        repo_state = self.get_repository_state(repository_root)

        if chain_name:
            run_id = repo_state.last_chain_runs.get(chain_name)
            if run_id:
                return self.get_chain_run(run_id)
            return None

        # Get most recent run for this repo
        for run_id in self._index.get("runs", []):
            run = self.get_chain_run(run_id)
            if run and run.repository_root == str(repository_root):
                return run

        return None

    def has_repository_changed(self, repository_root: Path) -> bool:
        """Check if repository has changed since last scan."""
        repo_state = self.get_repository_state(repository_root)

        if not repo_state.fingerprint:
            return True

        # Quick check: if git commit SHA changed, repository definitely changed
        current_git_sha = repo_state._get_git_commit_sha()
        if current_git_sha != repo_state.fingerprint.git_commit_sha:
            return True

        # Quick check: if critical files hash changed, repository changed
        current_critical_hash = None
        critical_files = repo_state._get_critical_files()
        critical_hashes = []
        for file_path in critical_files:
            if file_path.is_file():
                content_hash = repo_state._compute_file_content_hash(file_path)
                if content_hash:
                    relative_path = str(file_path.relative_to(str(repository_root)))
                    critical_hashes.append(f"{relative_path}:{content_hash}")

        if critical_hashes:
            combined = ":".join(sorted(critical_hashes))
            current_critical_hash = hashlib.sha256(combined.encode()).hexdigest()[:32]

        if current_critical_hash != repo_state.fingerprint.critical_files_hash:
            return True

        # Full fingerprint comparison as final check
        files = list(repository_root.rglob("*"))
        files = [f for f in files if f.is_file() and ".git" not in f.parts]

        # Recompute fingerprint without storing it
        temp_state = RepositoryState(repository_root=str(repository_root))
        temp_state.update_fingerprint(files)

        return temp_state.fingerprint.hash != repo_state.fingerprint.hash

    def cleanup_old_runs(self, keep_count: int = 100) -> int:
        """Remove old run records, keeping the most recent."""
        run_ids = self._index.get("runs", [])
        to_remove = run_ids[keep_count:]

        removed = 0
        for run_id in to_remove:
            run_file = self._runs_dir / f"{run_id}.json"
            if run_file.exists():
                run_file.unlink()
                removed += 1

        self._index["runs"] = run_ids[:keep_count]
        self._save_index()

        return removed

    # Agent execution tracking methods

    def start_agent_execution(
        self,
        agent_name: str,
        repository_root: Path,
        mode: str,
        caller: str = "api",
    ) -> AgentExecution:
        """
        Start tracking an agent execution.

        Creates and saves a new AgentExecution record with RUNNING status.
        """
        execution_id = self._get_execution_id()
        started_at = datetime.now(timezone.utc).isoformat()

        execution = AgentExecution(
            execution_id=execution_id,
            agent_name=agent_name,
            repository_root=str(repository_root.absolute()),
            status=RunStatus.RUNNING,
            mode=mode,
            started_at=started_at,
            caller=caller,
        )

        # Save execution record
        exec_file = self._agent_executions_dir / f"{execution_id}.json"
        exec_file.write_text(execution.model_dump_json(indent=2))

        # Update index
        self._index.setdefault("agent_executions", []).insert(0, execution_id)
        if len(self._index["agent_executions"]) > 1000:  # Keep last 1000
            self._index["agent_executions"] = self._index["agent_executions"][:1000]
        self._save_index()

        return execution

    def complete_agent_execution(
        self,
        execution_id: str,
        output_data: dict[str, Any] | None = None,
        error: str | None = None,
        execution_time_ms: float | None = None,
    ) -> AgentExecution | None:
        """
        Mark an agent execution as completed or failed.

        Updates the execution record with results and marks it COMPLETED or FAILED.
        """
        exec_file = self._agent_executions_dir / f"{execution_id}.json"
        if not exec_file.exists():
            return None

        try:
            data = json.loads(exec_file.read_text())
            execution = AgentExecution(**data)
        except (json.JSONDecodeError, ValueError):
            return None

        # Update execution
        execution.completed_at = datetime.now(timezone.utc).isoformat()
        execution.execution_time_ms = execution_time_ms

        if error:
            execution.status = RunStatus.FAILED
            execution.error = error
        else:
            execution.status = RunStatus.COMPLETED
            if output_data:
                execution.output_data = output_data

        # Save updated record
        exec_file.write_text(execution.model_dump_json(indent=2))

        return execution

    def get_agent_execution(self, execution_id: str) -> AgentExecution | None:
        """Get an agent execution by ID."""
        exec_file = self._agent_executions_dir / f"{execution_id}.json"
        if exec_file.exists():
            try:
                data = json.loads(exec_file.read_text())
                return AgentExecution(**data)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def list_running_executions(self) -> list[AgentExecution]:
        """List all currently running agent executions."""
        execution_ids = self._index.get("agent_executions", [])
        running = []

        for exec_id in execution_ids:
            execution = self.get_agent_execution(exec_id)
            if execution and execution.status == RunStatus.RUNNING:
                running.append(execution)

        return running

    def cleanup_old_executions(self, keep_count: int = 100) -> int:
        """Remove old agent execution records, keeping the most recent."""
        execution_ids = self._index.get("agent_executions", [])
        to_remove = execution_ids[keep_count:]

        removed = 0
        for exec_id in to_remove:
            exec_file = self._agent_executions_dir / f"{exec_id}.json"
            if exec_file.exists():
                exec_file.unlink()
                removed += 1

        self._index["agent_executions"] = execution_ids[:keep_count]
        self._save_index()

        return removed


@lru_cache(maxsize=1)
def get_state_manager() -> StateManager:
    """Get the global state manager (cached)."""
    return StateManager()
