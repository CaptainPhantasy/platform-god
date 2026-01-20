"""
Platform God Dashboard - Terminal UI dashboard.

Provides an interactive terminal-based dashboard for viewing:
- Repository overview
- Recent runs
- Agent status
- Findings summary
- Command palette

Falls back to static Rich-based display if Textual is not available.
"""

import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

# Try to import Textual for TUI, fall back gracefully
TEXTUAL_AVAILABLE = False
try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.reactive import reactive
    from textual.widgets import (
        DataTable,
        Footer,
        Header,
        Static,
        TabbedContent,
        TabPane,
        Input,
    )
    from textual.screen import ModalScreen
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

# Rich is always available (required dependency)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable


# =============================================================================
# Data Models
# =============================================================================

class RunStatus(str, Enum):
    """Status of a run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REPLAYING = "replaying"


class Severity(str, Enum):
    """Finding severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    NONE = "none"


@dataclass
class RepositoryInfo:
    """Information about a tracked repository."""
    id: int
    name: str
    description: str | None = None
    repository_url: str | None = None
    created_at: str = ""
    updated_at: str = ""
    is_active: bool = True
    governance_status: str = "active"


@dataclass
class RunInfo:
    """Information about a run."""
    id: int
    run_id: str
    run_type: str
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    initiated_by: str | None = None
    execution_time_ms: int | None = None
    project_name: str | None = None


@dataclass
class AgentInfo:
    """Information about an agent."""
    id: int
    name: str
    agent_type: str
    version: str
    description: str | None = None
    is_active: bool = True
    created_at: str = ""


@dataclass
class FindingInfo:
    """Information about a finding."""
    id: int
    finding_id: str
    severity: Severity
    category: str
    title: str
    description: str
    status: str = "open"
    location_path: str | None = None
    location_line: int | None = None
    created_at: str = ""
    project_name: str | None = None


@dataclass
class DashboardState:
    """Current state of the dashboard."""
    repositories: list[RepositoryInfo] = field(default_factory=list)
    runs: list[RunInfo] = field(default_factory=list)
    agents: list[AgentInfo] = field(default_factory=list)
    findings: list[FindingInfo] = field(default_factory=list)
    status_filter: str | None = None
    selected_repository: int | None = None
    last_refresh: str = ""


# =============================================================================
# Database Queries
# =============================================================================

class DashboardQueries:
    """Query the Platform God registry database."""

    def __init__(self, db_path: Path | None = None):
        """Initialize queries with database path."""
        if db_path is None:
            # Default to var/registry/platform_god.db
            db_path = Path("var/registry/platform_god.db")

        self._db_path = db_path
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _ensure_schema(self) -> bool:
        """Check if database has required tables."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row["name"] for row in cursor.fetchall()}
            required = {"projects", "runs", "agents", "findings"}
            return required.issubset(tables)
        except sqlite3.Error:
            return False

    def get_repositories(self) -> list[RepositoryInfo]:
        """Get all tracked repositories."""
        if not self._ensure_schema():
            return []

        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT id, name, description, repository_url, created_at, updated_at,
                       is_active, governance_status
                FROM projects
                ORDER BY updated_at DESC
                """
            )
            return [
                RepositoryInfo(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    repository_url=row["repository_url"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    is_active=bool(row["is_active"]),
                    governance_status=row["governance_status"],
                )
                for row in cursor.fetchall()
            ]
        except sqlite3.Error:
            return []

    def get_runs(
        self,
        limit: int = 50,
        status_filter: str | None = None,
        repository_id: int | None = None,
    ) -> list[RunInfo]:
        """Get recent runs."""
        if not self._ensure_schema():
            return []

        try:
            conn = self._get_connection()
            query = """
                SELECT r.id, r.run_id, r.run_type, r.status, r.started_at, r.completed_at,
                       r.initiated_by,
                       (SELECT execution_time_ms FROM agent_runs ar
                        WHERE ar.run_id = r.run_id LIMIT 1) as execution_time_ms,
                       p.name as project_name
                FROM runs r
                LEFT JOIN run_targets rt ON rt.run_id = r.run_id
                LEFT JOIN projects p ON p.id = rt.project_id
            """
            params: list[Any] = []

            conditions = []
            if status_filter:
                conditions.append("r.status = ?")
                params.append(status_filter)
            if repository_id:
                conditions.append("rt.project_id = ?")
                params.append(repository_id)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY r.started_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [
                RunInfo(
                    id=row["id"],
                    run_id=row["run_id"],
                    run_type=row["run_type"],
                    status=RunStatus(row["status"]),
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    initiated_by=row["initiated_by"],
                    execution_time_ms=row["execution_time_ms"],
                    project_name=row["project_name"],
                )
                for row in cursor.fetchall()
            ]
        except sqlite3.Error:
            return []

    def get_agents(self) -> list[AgentInfo]:
        """Get all registered agents."""
        if not self._ensure_schema():
            return []

        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT id, name, type, version, description, is_active, created_at
                FROM agents
                ORDER BY name
                """
            )
            return [
                AgentInfo(
                    id=row["id"],
                    name=row["name"],
                    agent_type=row["type"],
                    version=row["version"],
                    description=row["description"],
                    is_active=bool(row["is_active"]),
                    created_at=row["created_at"],
                )
                for row in cursor.fetchall()
            ]
        except sqlite3.Error:
            return []

    def get_findings(
        self,
        limit: int = 100,
        repository_id: int | None = None,
        severity_filter: Severity | None = None,
    ) -> list[FindingInfo]:
        """Get recent findings."""
        if not self._ensure_schema():
            return []

        try:
            conn = self._get_connection()
            query = """
                SELECT f.id, f.finding_id, f.severity, f.category, f.title, f.description,
                       f.status, f.location_path, f.location_line, f.created_at,
                       p.name as project_name
                FROM findings f
                LEFT JOIN projects p ON p.id = f.project_id
            """
            params: list[Any] = []
            conditions = []

            if repository_id:
                conditions.append("f.project_id = ?")
                params.append(repository_id)
            if severity_filter:
                conditions.append("f.severity = ?")
                params.append(severity_filter.value)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY f.created_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [
                FindingInfo(
                    id=row["id"],
                    finding_id=row["finding_id"],
                    severity=Severity(row["severity"]),
                    category=row["category"],
                    title=row["title"],
                    description=row["description"],
                    status=row["status"],
                    location_path=row["location_path"],
                    location_line=row["location_line"],
                    created_at=row["created_at"],
                    project_name=row["project_name"],
                )
                for row in cursor.fetchall()
            ]
        except sqlite3.Error:
            return []

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics for the dashboard."""
        if not self._ensure_schema():
            return {}

        try:
            conn = self._get_connection()
            stats: dict[str, Any] = {}

            # Project count
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM projects WHERE is_active = 1"
            )
            stats["active_projects"] = cursor.fetchone()["count"]

            # Run counts by status
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM runs
                GROUP BY status
                """
            )
            stats["runs_by_status"] = {r["status"]: r["count"] for r in cursor.fetchall()}

            # Agent count
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM agents WHERE is_active = 1"
            )
            stats["active_agents"] = cursor.fetchone()["count"]

            # Finding counts by severity
            cursor = conn.execute(
                """
                SELECT severity, COUNT(*) as count
                FROM findings
                WHERE status = 'open'
                GROUP BY severity
                """
            )
            stats["findings_by_severity"] = {
                r["severity"]: r["count"] for r in cursor.fetchall()
            }

            return stats
        except sqlite3.Error:
            return {}

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# =============================================================================
# Fallback UI (Rich-based static display)
# =============================================================================

class FallbackDashboard:
    """Fallback Rich-based dashboard when Textual is not available."""

    def __init__(self, queries: DashboardQueries):
        """Initialize fallback dashboard."""
        self.queries = queries
        self.console = Console()

    def _format_status(self, status: str) -> str:
        """Format status with color."""
        status_colors = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
            "pending": "dim",
            "cancelled": "grey",
        }
        color = status_colors.get(status, "white")
        return f"[{color}]{status}[/{color}]"

    def _format_severity(self, severity: str) -> str:
        """Format severity with color."""
        severity_colors = {
            "critical": "bold red",
            "high": "red",
            "medium": "yellow",
            "low": "cyan",
            "info": "dim",
        }
        color = severity_colors.get(severity, "white")
        return f"[{color}]{severity.upper()}[/{color}]"

    def _format_timestamp(self, ts: str) -> str:
        """Format timestamp for display."""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            return ts[:19] if ts else "-"

    def show(self) -> None:
        """Display the static dashboard."""
        # Load data
        repos = self.queries.get_repositories()
        runs = self.queries.get_runs(limit=20)
        agents = self.queries.get_agents()
        findings = self.queries.get_findings(limit=30)
        stats = self.queries.get_summary_stats()

        # Clear screen
        self.console.clear()

        # Title
        self.console.print()
        self.console.print(
            Panel.fit(
                "[bold blue]Platform God[/bold blue] - Dashboard",
                subtitle="Press 'r' to refresh, 'q' to quit (requires textual for interactive mode)",
            )
        )
        self.console.print()

        # Summary stats row
        stats_grid = RichTable(show_header=False, box=None, padding=(0, 2))
        stats_grid.add_column()
        stats_grid.add_column()
        stats_grid.add_column()
        stats_grid.add_column()

        active_projects = stats.get("active_projects", 0)
        active_agents = stats.get("active_agents", 0)
        runs_by_status = stats.get("runs_by_status", {})
        completed_runs = runs_by_status.get("completed", 0)
        findings_by_severity = stats.get("findings_by_severity", {})
        open_findings = sum(findings_by_severity.values())

        stats_grid.add_row(
            f"[cyan]Projects:[/cyan] {active_projects}",
            f"[cyan]Agents:[/cyan] {active_agents}",
            f"[cyan]Runs (completed):[/cyan] {completed_runs}",
            f"[cyan]Open Findings:[/cyan] {open_findings}",
        )
        self.console.print(stats_grid)
        self.console.print()

        # Repositories panel
        if repos:
            repo_table = RichTable(title=f"Repositories ({len(repos)})")
            repo_table.add_column("Name", style="cyan")
            repo_table.add_column("Status")
            repo_table.add_column("Governance")
            repo_table.add_column("Updated")

            for repo in repos[:10]:
                status = "[green]active[/green]" if repo.is_active else "[dim]inactive[/dim]"
                repo_table.add_row(
                    repo.name,
                    status,
                    repo.governance_status,
                    self._format_timestamp(repo.updated_at),
                )

            self.console.print(repo_table)
            self.console.print()

        # Recent runs panel
        if runs:
            runs_table = RichTable(title=f"Recent Runs ({len(runs)})")
            runs_table.add_column("Run ID", style="cyan")
            runs_table.add_column("Type")
            runs_table.add_column("Project")
            runs_table.add_column("Status")
            runs_table.add_column("Started")

            for run in runs[:15]:
                runs_table.add_row(
                    run.run_id[:12],
                    run.run_type,
                    run.project_name or "-",
                    self._format_status(run.status.value),
                    self._format_timestamp(run.started_at),
                )

            self.console.print(runs_table)
            self.console.print()

        # Agents panel
        if agents:
            agents_table = RichTable(title=f"Agents ({len(agents)})")
            agents_table.add_column("Name", style="cyan")
            agents_table.add_column("Type")
            agents_table.add_column("Version")
            agents_table.add_column("Status")

            for agent in agents[:15]:
                status = "[green]active[/green]" if agent.is_active else "[dim]inactive[/dim]"
                agents_table.add_row(
                    agent.name,
                    agent.agent_type,
                    agent.version,
                    status,
                )

            self.console.print(agents_table)
            self.console.print()

        # Findings panel
        if findings:
            findings_table = RichTable(title=f"Recent Findings ({len(findings)})")
            findings_table.add_column("Severity")
            findings_table.add_column("Category")
            findings_table.add_column("Title", style="yellow")
            findings_table.add_column("Status")
            findings_table.add_column("Location")

            for finding in findings[:15]:
                location = finding.location_path or "-"
                if finding.location_line:
                    location += f":{finding.location_line}"

                findings_table.add_row(
                    self._format_severity(finding.severity.value),
                    finding.category,
                    finding.title[:40] + "..." if len(finding.title) > 40 else finding.title,
                    finding.status,
                    location[:30] + "..." if len(location) > 30 else location,
                )

            self.console.print(findings_table)
            self.console.print()

        self.console.print(
            "[dim]Tip: Install textual for interactive TUI: pip install textual[/dim]"
        )
        self.console.print()


# =============================================================================
# Textual TUI Implementation
# =============================================================================

if TEXTUAL_AVAILABLE:

    class CommandPalette(ModalScreen):
        """Command palette for quick actions."""

        CSS = """
        CommandPalette {
            align: center middle;
        }

        #command-dialog {
            width: 60;
            height: 20;
            border: thick $primary;
            background: $surface;
        }

        #command-input {
            width: 1fr;
            margin: 1 2;
        }

        #command-list {
            height: 1fr;
            margin: 0 2 1 2;
            border-top: solid $primary;
        }
        """

        COMMANDS = [
            ("refresh", "Refresh all data"),
            ("filter:all", "Show all runs"),
            ("filter:completed", "Show completed runs only"),
            ("filter:failed", "Show failed runs only"),
            ("filter:running", "Show running runs only"),
            ("quit", "Exit dashboard"),
        ]

        def compose(self) -> ComposeResult:
            with Vertical(id="command-dialog"):
                yield Input(
                    placeholder="Type a command...",
                    id="command-input",
                )
                yield Static(
                    "\n".join(f"  {cmd} - {desc}" for cmd, desc in self.COMMANDS),
                    id="command-list",
                )

        def on_input_submitted(self, event: Input.Changed) -> None:
            """Handle command submission."""
            cmd = event.value.strip().lower()
            self.dismiss(cmd)


    class DashboardApp(App):
        """Main Textual TUI dashboard application."""

        CSS = """
        DashboardApp {
            background: $background;
        }

        Header {
            text-align: center;
            background: $primary;
            text-style: bold;
        }

        .panel {
            padding: 0 1;
        }

        DataTable {
            height: 1fr;
        }

        #stats-container {
            height: 3;
        }

        .stat-box {
            width: 1fr;
            padding: 1;
            background: $surface;
            border: solid $primary;
            border-subtitle-align: center;
        }
        """

        BINDINGS = [
            Binding("r", "refresh", "Refresh"),
            Binding("q,ctrl+c", "quit", "Quit"),
            Binding("f", "filter", "Filter runs"),
            Binding("ctrl+p", "command_palette", "Commands"),
            Binding("tab", "focus_next", "Focus Next"),
            Binding("shift+tab", "focus_previous", "Focus Previous"),
        ]

        state: reactive[DashboardState] = reactive(DashboardState)

        def __init__(self, db_path: Path | None = None):
            """Initialize the dashboard."""
            super().__init__()
            self.queries = DashboardQueries(db_path)
            self._db_path = db_path

        def on_mount(self) -> None:
            """Initialize dashboard on mount."""
            self.refresh_data()

        def refresh_data(self) -> None:
            """Refresh all data from the database."""
            repos = self.queries.get_repositories()
            runs = self.queries.get_runs(
                limit=50,
                status_filter=self.state.status_filter,
            )
            agents = self.queries.get_agents()
            findings = self.queries.get_findings(limit=100)

            self.state = DashboardState(
                repositories=repos,
                runs=runs,
                agents=agents,
                findings=findings,
                status_filter=self.state.status_filter,
                last_refresh=datetime.now(timezone.utc).isoformat(),
            )

            # Update UI
            self._update_stats()
            self._update_runs_table()
            self._update_agents_table()
            self._update_findings_table()
            self._update_repos_table()

        def _update_stats(self) -> None:
            """Update summary statistics."""
            stats_box = self.query_one("#stats", Static)
            stats = self.queries.get_summary_stats()

            runs_by_status = stats.get("runs_by_status", {})
            findings_by_severity = stats.get("findings_by_severity", {})

            critical = findings_by_severity.get("critical", 0)
            high = findings_by_severity.get("high", 0)
            medium = findings_by_severity.get("medium", 0)
            open_count = critical + high + medium

            stats_text = (
                f"[cyan]Projects:[/cyan] {stats.get('active_projects', 0)} | "
                f"[cyan]Agents:[/cyan] {stats.get('active_agents', 0)} | "
                f"[cyan]Runs:[/cyan] {runs_by_status.get('completed', 0)} completed, "
                f"{runs_by_status.get('failed', 0)} failed | "
                f"[red]Open Findings:[/red] {open_count}"
            )
            stats_box.update(stats_text)

        def _update_repos_table(self) -> None:
            """Update repositories table."""
            table = self.query_one("#repos-table", DataTable)
            table.clear()

            for repo in self.state.repositories:
                status = "active" if repo.is_active else "inactive"
                table.add_row(
                    repo.name,
                    status,
                    repo.governance_status,
                    repo.updated_at[:19] if repo.updated_at else "-",
                )

        def _update_runs_table(self) -> None:
            """Update runs table."""
            table = self.query_one("#runs-table", DataTable)
            table.clear()

            for run in self.state.runs:
                status_style = {
                    "completed": "green",
                    "failed": "red",
                    "running": "yellow",
                    "pending": "dim",
                }.get(run.status.value, "white")

                table.add_row(
                    run.run_id[:12],
                    run.run_type,
                    run.project_name or "-",
                    f"[{status_style}]{run.status.value}[/{status_style}]",
                    run.started_at[:16] if run.started_at else "-",
                )

        def _update_agents_table(self) -> None:
            """Update agents table."""
            table = self.query_one("#agents-table", DataTable)
            table.clear()

            for agent in self.state.agents:
                status = "active" if agent.is_active else "inactive"
                table.add_row(
                    agent.name,
                    agent.agent_type,
                    agent.version,
                    status,
                )

        def _update_findings_table(self) -> None:
            """Update findings table."""
            table = self.query_one("#findings-table", DataTable)
            table.clear()

            for finding in self.state.findings:
                severity_style = {
                    "critical": "bold red",
                    "high": "red",
                    "medium": "yellow",
                    "low": "cyan",
                    "info": "dim",
                }.get(finding.severity.value, "white")

                location = finding.location_path or "-"
                if finding.location_line:
                    location += f":{finding.location_line}"

                table.add_row(
                    f"[{severity_style}]{finding.severity.value.upper()}[/{severity_style}]",
                    finding.category,
                    finding.title[:50] + "..." if len(finding.title) > 50 else finding.title,
                    finding.status,
                    location[:30] + "..." if len(location) > 30 else location,
                )

        def compose(self) -> ComposeResult:
            """Compose the dashboard UI."""
            yield Header()
            yield Header(show_clock=True)

            with Vertical():
                # Summary stats
                yield Static("", id="stats")

                # Tabbed content
                with TabbedContent():
                    with TabPane("Runs", id="runs-tab"):
                        yield DataTable(id="runs-table")
                    with TabPane("Repositories", id="repos-tab"):
                        yield DataTable(id="repos-table")
                    with TabPane("Findings", id="findings-tab"):
                        yield DataTable(id="findings-table")
                    with TabPane("Agents", id="agents-tab"):
                        yield DataTable(id="agents-table")

            yield Footer()

        def on_mount(self) -> None:
            """Initialize tables on mount."""
            super().on_mount()

            # Setup runs table
            runs_table = self.query_one("#runs-table", DataTable)
            runs_table.add_column("Run ID", key="run_id")
            runs_table.add_column("Type", key="type")
            runs_table.add_column("Project", key="project")
            runs_table.add_column("Status", key="status")
            runs_table.add_column("Started", key="started")
            runs_table.cursor_type = "row"

            # Setup repositories table
            repos_table = self.query_one("#repos-table", DataTable)
            repos_table.add_column("Name", key="name")
            repos_table.add_column("Status", key="status")
            repos_table.add_column("Governance", key="governance")
            repos_table.add_column("Updated", key="updated")
            repos_table.cursor_type = "row"

            # Setup findings table
            findings_table = self.query_one("#findings-table", DataTable)
            findings_table.add_column("Severity", key="severity")
            findings_table.add_column("Category", key="category")
            findings_table.add_column("Title", key="title")
            findings_table.add_column("Status", key="status")
            findings_table.add_column("Location", key="location")
            findings_table.cursor_type = "row"

            # Setup agents table
            agents_table = self.query_one("#agents-table", DataTable)
            agents_table.add_column("Name", key="name")
            agents_table.add_column("Type", key="type")
            agents_table.add_column("Version", key="version")
            agents_table.add_column("Status", key="status")
            agents_table.cursor_type = "row"

            # Initial data load
            self.refresh_data()

        def action_refresh(self) -> None:
            """Refresh dashboard data."""
            self.refresh_data()

        def action_filter(self) -> None:
            """Cycle through run status filters."""
            filters = [None, "completed", "failed", "running"]
            current_idx = filters.index(self.state.status_filter) if self.state.status_filter in filters else 0
            next_filter = filters[(current_idx + 1) % len(filters)]

            self.state.status_filter = next_filter
            self.refresh_data()

        def action_command_palette(self) -> None:
            """Open command palette."""
            async def on_result(command: str | None) -> None:
                if command == "quit":
                    self.exit()
                elif command == "refresh" or command == "filter:all":
                    self.state.status_filter = None
                    self.refresh_data()
                elif command == "filter:completed":
                    self.state.status_filter = "completed"
                    self.refresh_data()
                elif command == "filter:failed":
                    self.state.status_filter = "failed"
                    self.refresh_data()
                elif command == "filter:running":
                    self.state.status_filter = "running"
                    self.refresh_data()

            self.push_screen(CommandPalette(), on_result)


# =============================================================================
# Main Entry Point
# =============================================================================

def launch_dashboard(
    db_path: Path | None = None,
    force_fallback: bool = False,
) -> int:
    """
    Launch the dashboard.

    Args:
        db_path: Path to SQLite registry database
        force_fallback: Force use of fallback UI even if Textual is available

    Returns:
        Exit code (0 for success, 1 for error)
    """
    queries = DashboardQueries(db_path)

    # Verify database exists and has data
    if not queries._ensure_schema():
        console = Console()
        console.print("[yellow]Warning:[/yellow] Database schema not found or incomplete.")
        console.print("Expected tables: projects, runs, agents, findings")
        console.print(f"Database path: {queries._db_path}")
        console.print("\nRun a chain first to populate the database:")
        console.print("  platform-god run discovery /path/to/repo --record")
        return 1

    # Check if we have any data
    stats = queries.get_summary_stats()
    has_data = (
        stats.get("active_projects", 0) > 0
        or stats.get("runs_by_status", {})
        or stats.get("active_agents", 0) > 0
    )

    if not has_data:
        console = Console()
        console.print("[yellow]Warning:[/yellow] No data found in registry.")
        console.print("Run a chain first to populate the database:")
        console.print("  platform-god run discovery /path/to/repo --record")
        # Continue anyway to show empty dashboard

    # Choose UI based on Textual availability
    if TEXTUAL_AVAILABLE and not force_fallback:
        try:
            app = DashboardApp(db_path)
            app.run()
            return 0
        except Exception as e:
            console = Console()
            console.print(f"[red]Error launching TUI:[/red] {e}")
            console.print("Falling back to static display...")
            fallback = FallbackDashboard(queries)
            fallback.show()
            return 0
    else:
        fallback = FallbackDashboard(queries)
        fallback.show()
        return 0


def main() -> int:
    """
    Main entry point for dashboard command.

    Can be called directly or imported as a module.
    """
    import sys

    db_path = None
    force_fallback = False

    # Parse simple args
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    for arg in args:
        if arg.startswith("--db="):
            db_path = Path(arg.split("=", 1)[1])
        elif arg == "--fallback":
            force_fallback = True
        elif arg in ("-h", "--help"):
            print("Platform God Dashboard")
            print("\nUsage: python -m platform_god.dashboard [options]")
            print("\nOptions:")
            print("  --db=PATH     Path to SQLite database (default: var/registry/platform_god.db)")
            print("  --fallback    Force fallback UI (don't use Textual)")
            print("  -h, --help    Show this help")
            return 0

    return launch_dashboard(db_path, force_fallback)


if __name__ == "__main__":
    import sys
    sys.exit(main())
