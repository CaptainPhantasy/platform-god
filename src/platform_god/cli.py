"""
Platform God CLI - Command-line interface.

Run agents, chains, and inspections from the terminal.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from platform_god.agents.executor import ExecutionMode
from platform_god.agents.registry import AgentClass, get_global_registry
from platform_god.orchestrator.core import ChainDefinition, Orchestrator

app = typer.Typer(
    name="platform-god",
    help="Platform God - Deterministic Agent-Driven Repository Governance",
    no_args_is_help=True,
)
console = Console()


@app.command()
def agents(
    class_filter: Optional[AgentClass] = typer.Option(
        None, "--class", "-c", help="Filter by agent class"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List all available agents."""
    registry = get_global_registry()

    if class_filter:
        agent_list = registry.list_class(class_filter)
    else:
        agent_list = registry.list_all()

    table = Table(title=f"Registered Agents ({len(agent_list)})")
    table.add_column("Name", style="cyan")
    table.add_column("Class", style="magenta")
    table.add_column("Permissions")

    for agent in agent_list:
        permissions = agent.permissions.value
        if verbose:
            permissions += f"\nAllowed: {', '.join(agent.allowed_paths) or 'none'}"

        table.add_row(agent.name, agent.agent_class.value, permissions)

    console.print(table)


@app.command()
def chains():
    """List available execution chains."""
    table = Table(title="Execution Chains")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Steps", style="green")

    chains = [
        ChainDefinition.discovery_chain(),
        ChainDefinition.security_scan_chain(),
        ChainDefinition.dependency_audit_chain(),
        ChainDefinition.doc_generation_chain(),
        ChainDefinition.tech_debt_chain(),
        ChainDefinition.full_analysis_chain(),
    ]

    for chain in chains:
        steps = "\n".join(f"  {i+1}. {s.agent_name}" for i, s in enumerate(chain.steps))
        table.add_row(chain.name, chain.description, steps)

    console.print(table)


@app.command()
def run(
    chain_name: str = typer.Argument(..., help="Chain to execute"),
    repo_path: Path = typer.Argument(..., help="Path to repository"),
    mode: ExecutionMode = typer.Option(
        ExecutionMode.DRY_RUN,
        "--mode",
        "-m",
        help="Execution mode",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    record: bool = typer.Option(False, "--record", "-r", help="Record run in state"),
):
    """Execute an agent chain."""
    console.print(
        Panel.fit(
            f"[bold blue]Platform God[/bold blue]\n"
            f"Chain: {chain_name}\n"
            f"Repository: {repo_path}\n"
            f"Mode: {mode.value}",
        )
    )

    # Get chain definition
    chain_map = {
        "discovery_analysis": ChainDefinition.discovery_chain,
        "discovery": ChainDefinition.discovery_chain,
        "security_scan": ChainDefinition.security_scan_chain,
        "security": ChainDefinition.security_scan_chain,
        "dependency_audit": ChainDefinition.dependency_audit_chain,
        "dependencies": ChainDefinition.dependency_audit_chain,
        "deps": ChainDefinition.dependency_audit_chain,
        "doc_generation": ChainDefinition.doc_generation_chain,
        "docs": ChainDefinition.doc_generation_chain,
        "documentation": ChainDefinition.doc_generation_chain,
        "tech_debt": ChainDefinition.tech_debt_chain,
        "debt": ChainDefinition.tech_debt_chain,
        "full_analysis": ChainDefinition.full_analysis_chain,
        "full": ChainDefinition.full_analysis_chain,
        "all": ChainDefinition.full_analysis_chain,
    }

    chain_factory = chain_map.get(chain_name)
    if not chain_factory:
        console.print(f"[red]Unknown chain: {chain_name}[/red]")
        raise typer.Exit(1)

    chain = chain_factory()

    # Execute
    orchestrator = Orchestrator()
    result = orchestrator.execute_chain(chain, repo_path, mode)

    # Print summary
    console.print("\n")
    console.print(orchestrator.chain_summary(result))

    # Record in state if requested
    if record:
        chain_run = orchestrator.record_chain_run(result, repo_path)
        console.print(f"\n[green]Run recorded:[/green] {chain_run.run_id}")

    # Persist if requested
    if output:
        output_path = orchestrator.persist_chain_result(result, output.parent or Path("."))
        console.print(f"\n[green]Results saved to:[/green] {output_path}")

    # Exit code based on status
    if result.status.value != "completed":
        raise typer.Exit(1)


@app.command()
def inspect(
    repo_path: Path = typer.Argument(..., help="Path to repository"),
):
    """Quick inspection of repository structure."""
    console.print(
        Panel.fit(
            f"[bold blue]Repository Inspection[/bold blue]\n"
            f"Path: {repo_path}",
        )
    )

    if not repo_path.exists():
        console.print(f"[red]Path does not exist: {repo_path}[/red]")
        raise typer.Exit(1)

    # Count files by extension
    from collections import Counter

    extensions = Counter()
    total_files = 0
    total_size = 0

    for item in repo_path.rglob("*"):
        if item.is_file() and ".git" not in item.parts:
            total_files += 1
            total_size += item.stat().st_size
            ext = item.suffix or "(no ext)"
            extensions[ext] += 1

    table = Table(title="File Summary")
    table.add_column("Extension", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Percent", justify="right")

    for ext, count in extensions.most_common(10):
        percent = (count / total_files) * 100
        table.add_row(ext, str(count), f"{percent:.1f}%")

    console.print(table)
    console.print(f"\nTotal files: {total_files}")
    console.print(f"Total size: {total_size:,} bytes")


@app.command()
def history(
    repo_path: Path = typer.Argument(..., help="Path to repository"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of runs to show"),
):
    """Show chain execution history for a repository."""
    from platform_god.state.manager import StateManager

    state_mgr = StateManager()
    runs = state_mgr.list_runs(repo_path, limit=limit)

    if not runs:
        console.print("[yellow]No chain runs found for this repository[/yellow]")
        return

    table = Table(title=f"Execution History ({len(runs)} runs)")
    table.add_column("Time", style="cyan")
    table.add_column("Chain")
    table.add_column("Status")
    table.add_column("Duration")
    table.add_column("Run ID", style="dim")

    for run in runs:
        status_style = "green" if run.status.value == "completed" else "red"
        duration = f"{run.execution_time_ms:.0f}ms" if run.execution_time_ms else "-"
        table.add_row(
            run.started_at[:19],
            run.chain_name,
            f"[{status_style}]{run.status.value}[/{status_style}]",
            duration,
            run.run_id[:12],
        )

    console.print(table)


@app.command()
def ui(
    repo_path: Path = typer.Argument(..., help="Path to repository"),
    dashboard: bool = typer.Option(False, "--dashboard", "-d", help="Launch Ink dashboard mode"),
):
    """
    Launch the read-only UI (Node.js + Ink).

    CLI mode (default): Text-based output of runs, findings, and artifacts.
    Dashboard mode (--dashboard): Interactive TUI with keyboard navigation.
    """
    # Find the ui directory
    here = Path(__file__).parent
    ui_dir = here.parent.parent / "ui"
    ui_script = ui_dir / "index.js"

    if not ui_script.exists():
        console.print(f"[red]UI not found at: {ui_script}[/red]")
        console.print("[yellow]Install Node.js dependencies:[/yellow]")
        console.print("  cd ui && npm install")
        raise typer.Exit(1)

    # Check if node is available
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True, shell=False)
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[red]Node.js not found. Please install Node.js 18+ to use the UI.[/red]")
        raise typer.Exit(1)

    # Build command
    cmd = ["node", str(ui_script), "--repo", str(repo_path.absolute())]
    if dashboard:
        cmd.append("--dashboard")

    # Run the UI
    try:
        result = subprocess.run(cmd, check=True, shell=False)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]UI exited with error: {e.returncode}[/red]")
        raise typer.Exit(e.returncode)
    except KeyboardInterrupt:
        console.print("\n[yellow]UI interrupted[/yellow]")
        raise typer.Exit(0)


@app.command()
def version():
    """Show Platform God version."""
    from platform_god import __version__

    console.print(f"Platform God v{__version__}")


@app.command("monitor")
def monitor_cmd(
    health: bool = typer.Option(False, "--health", "-h", help="Show health check status"),
    metrics: bool = typer.Option(False, "--metrics", "-m", help="Show execution metrics"),
    recent: int = typer.Option(10, "--recent", "-n", help="Number of recent runs to show"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Watch mode (auto-refresh)"),
):
    """
    Show system status, recent runs, and health indicators.

    Displays:
    - System status (health)
    - Registry statistics
    - Recent agent runs
    - Health indicators
    """
    from platform_god.monitoring.health import run_all_health_checks, get_overall_health, HealthStatus
    from platform_god.monitoring.metrics import get_metrics_collector
    from platform_god.state.manager import StateManager
    from platform_god.registry.storage import Registry

    def display_monitor():
        # Health checks
        if health:
            console.print(Panel.fit("[bold blue]Health Status[/bold blue]"))
            results = run_all_health_checks(include_llm=False)
            overall = get_overall_health(results)

            # Overall status
            status_style = {
                HealthStatus.HEALTHY: "green",
                HealthStatus.DEGRADED: "yellow",
                HealthStatus.UNHEALTHY: "red",
                HealthStatus.UNKNOWN: "dim",
            }.get(overall, "white")

            console.print(f"Overall: [{status_style}]{overall.value.upper()}[/{status_style}]\n")

            # Individual checks
            health_table = Table(show_header=False, box=None)
            health_table.add_column("Check", style="cyan")
            health_table.add_column("Status")
            health_table.add_column("Details", dim=True)

            for name, result in results.items():
                result_style = {
                    HealthStatus.HEALTHY: "green",
                    HealthStatus.DEGRADED: "yellow",
                    HealthStatus.UNHEALTHY: "red",
                    HealthStatus.UNKNOWN: "dim",
                }.get(result.status, "white")

                health_table.add_row(
                    name,
                    f"[{result_style}]{result.status.value}[/{result_style}]",
                    result.message[:50] + "..." if len(result.message) > 50 else result.message,
                )

            console.print(health_table)
            console.print()

        # Metrics
        if metrics:
            console.print(Panel.fit("[bold blue]Execution Metrics[/bold blue]"))
            collector = get_metrics_collector()
            all_metrics = collector.get_all_metrics()

            # System metrics
            sys_metrics = all_metrics.get("system", {})
            console.print(f"Total agent executions: {sys_metrics.get('total_agent_executions', 0)}")
            console.print(f"Total chain executions: {sys_metrics.get('total_chain_executions', 0)}")
            console.print(f"Total errors: {sys_metrics.get('total_errors', 0)}")
            console.print(f"Active repositories: {sys_metrics.get('active_repositories', 0)}")
            console.print(f"Registry entities: {sys_metrics.get('registry_entities', 0)}")
            console.print()

            # Top agents by execution count
            agent_metrics = all_metrics.get("agents", [])
            if agent_metrics:
                # Sort by execution count
                agent_metrics.sort(key=lambda x: x.get("execution_count", 0), reverse=True)
                top_agents = agent_metrics[:5]

                agent_table = Table(title="Top Agents")
                agent_table.add_column("Agent", style="cyan")
                agent_table.add_column("Executions", justify="right")
                agent_table.add_column("Success Rate", justify="right")
                agent_table.add_column("Avg Time (ms)", justify="right")

                for agent in top_agents:
                    success_rate = agent.get("success_rate", 0)
                    rate_style = "green" if success_rate >= 90 else "yellow" if success_rate >= 70 else "red"
                    agent_table.add_row(
                        agent.get("agent_name", "unknown"),
                        str(agent.get("execution_count", 0)),
                        f"[{rate_style}]{success_rate:.1f}%[/{rate_style}]",
                        f"{agent.get('average_execution_time_ms', 0):.0f}",
                    )

                console.print(agent_table)
                console.print()

            # Chain metrics
            chain_metrics = all_metrics.get("chains", [])
            if chain_metrics:
                chain_metrics.sort(key=lambda x: x.get("execution_count", 0), reverse=True)
                top_chains = chain_metrics[:5]

                chain_table = Table(title="Chain Executions")
                chain_table.add_column("Chain", style="cyan")
                chain_table.add_column("Executions", justify="right")
                chain_table.add_column("Success Rate", justify="right")
                chain_table.add_column("Avg Time (ms)", justify="right")

                for chain in top_chains:
                    success_rate = chain.get("success_rate", 0)
                    rate_style = "green" if success_rate >= 90 else "yellow" if success_rate >= 70 else "red"
                    chain_table.add_row(
                        chain.get("chain_name", "unknown"),
                        str(chain.get("execution_count", 0)),
                        f"[{rate_style}]{success_rate:.1f}%[/{rate_style}]",
                        f"{chain.get('average_execution_time_ms', 0):.0f}",
                    )

                console.print(chain_table)
                console.print()

        # Registry stats (always show unless specific flags)
        if not health and not metrics:
            console.print(Panel.fit("[bold blue]Registry Statistics[/bold blue]"))
            registry = Registry()

            entity_counts = {
                entity_type: len(entity_ids)
                for entity_type, entity_ids in registry.index.entities.items()
            }
            total_entities = sum(entity_counts.values())

            console.print(f"Total entities: {total_entities}")
            console.print(f"Index version: {registry.index.version}")
            console.print(f"Last updated: {registry.index.last_updated}")

            if entity_counts:
                console.print("\nEntities by type:")
                for entity_type, count in sorted(entity_counts.items()):
                    console.print(f"  {entity_type}: {count}")
            console.print()

        # Recent runs (always show unless specific flags)
        if not health and not metrics:
            console.print(Panel.fit("[bold blue]Recent Runs[/bold blue]"))
            state_mgr = StateManager()
            runs = state_mgr.list_runs(limit=recent)

            if not runs:
                console.print("[yellow]No chain runs found[/yellow]")
            else:
                runs_table = Table()
                runs_table.add_column("Time", style="cyan")
                runs_table.add_column("Chain")
                runs_table.add_column("Repository")
                runs_table.add_column("Status")
                runs_table.add_column("Duration", justify="right")

                for run in runs:
                    status_style = "green" if run.status.value == "completed" else "red"
                    repo_name = Path(run.repository_root).name
                    duration = f"{run.execution_time_ms:.0f}ms" if run.execution_time_ms else "-"

                    runs_table.add_row(
                        run.started_at[:16].replace("T", " "),
                        run.chain_name,
                        repo_name,
                        f"[{status_style}]{run.status.value}[/{status_style}]",
                        duration,
                    )

                console.print(runs_table)
            console.print()

        # Default summary if no flags
        if not health and not metrics:
            # Show quick health indicators
            results = run_all_health_checks(include_llm=False)
            overall = get_overall_health(results)

            status_style = {
                HealthStatus.HEALTHY: "green",
                HealthStatus.DEGRADED: "yellow",
                HealthStatus.UNHEALTHY: "red",
            }.get(overall, "white")

            console.print(Panel.fit(
                f"[bold]System Status:[/bold] [{status_style}]{overall.value.upper()}[/{status_style}]",
                title="Summary"
            ))

    # Watch mode
    if watch:
        import time

        console.print("\n[bold yellow]WATCH MODE ACTIVE[/bold yellow]")
        console.print("[dim]Press Ctrl+C to exit[/dim]\n")
        refresh_interval = 5

        try:
            iteration = 0
            while True:
                iteration += 1

                # Show refresh header on first run and periodically
                if iteration == 1:
                    console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]")
                    console.print("[bold cyan]  Platform God Monitor - Watch Mode[/bold cyan]")
                    console.print("[bold cyan]" + "=" * 60 + "[/bold cyan]\n")

                # Display the monitor content
                display_monitor()

                # Show countdown to next refresh
                console.print()
                for remaining in range(refresh_interval, 0, -1):
                    countdown_bar = "━" * remaining + "░" * (refresh_interval - remaining)
                    console.print(
                        f"\r[bold cyan]Refreshing in:[/bold cyan] "
                        f"[cyan]{remaining}s[/cyan] "
                        f"[dim]{countdown_bar}[/dim] "
                        f"[dim](Ctrl+C to exit)[/dim]",
                        end=""
                    )
                    time.sleep(1)

                # Clear only the status line before next refresh
                console.print("\r" + " " * 80 + "\r", end="")

        except KeyboardInterrupt:
            console.print("\r" + " " * 80 + "\r", end="")  # Clear the countdown line
            console.print("\n[bold yellow]Watch mode ended[/bold yellow]")
            console.print("[dim]Press Enter to return to prompt[/dim]")
    else:
        display_monitor()


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
