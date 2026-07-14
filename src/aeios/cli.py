from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aeios import __version__
from aeios.core.kernel import Kernel

app = typer.Typer(
    name="aeios",
    help="AEIOS — AI Engineering Operating System",
    no_args_is_help=True,
)
task_app = typer.Typer(help="Inspect persisted tasks")
app.add_typer(task_app, name="task")
console = Console()


def _kernel(workspace: Optional[Path] = None) -> Kernel:
    return Kernel(workspace=workspace or Path.cwd())


@app.command()
def version() -> None:
    """Print AEIOS version."""
    console.print(f"aeios {__version__}")


@app.command()
def status() -> None:
    """Show kernel health and registered agents/tools."""
    k = _kernel()
    info = k.status()
    table = Table(title="AEIOS Kernel Status")
    table.add_column("Key")
    table.add_column("Value")
    for key in (
        "version",
        "env",
        "workspace",
        "db_path",
        "tasks_tracked",
        "last_task_id",
        "llm_planner",
    ):
        table.add_row(key, str(info.get(key)))
    table.add_row("agents", ", ".join(info["agents"]))
    table.add_row("tools", ", ".join(info["tools"]))
    table.add_row(
        "scheduler",
        f"pending={info['scheduler']['pending']} active={info['scheduler']['active']}",
    )
    console.print(table)


@app.command()
def doctor() -> None:
    """Run health checks for local AEIOS setup."""
    report = _kernel().syscalls.doctor()
    table = Table(title="AEIOS Doctor")
    table.add_column("Check")
    table.add_column("OK")
    table.add_column("Detail")
    for check in report["checks"]:
        table.add_row(
            check["name"],
            "[green]yes[/green]" if check["ok"] else "[yellow]no[/yellow]",
            str(check["detail"]),
        )
    console.print(table)
    if report["ok"]:
        console.print("[green]Kernel ready.[/green]")
        raise typer.Exit(0)
    console.print("[red]Kernel has blocking issues.[/red]")
    raise typer.Exit(1)


@app.command("run")
def run_goal(
    goal: str = typer.Argument(..., help="High-level goal for the kernel"),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        "-a",
        help="Agent name (echo | software_engineer | architect)",
    ),
) -> None:
    """Submit a goal to the kernel (plan → act → observe)."""
    k = _kernel()
    task = k.syscalls.execute_task(goal, agent=agent)

    style = "green" if task.status.value == "completed" else "red"
    console.print(
        Panel.fit(
            f"[bold]{task.status.value}[/bold]\n"
            f"id: {task.id}\n"
            f"agent: {task.agent}\n"
            f"goal: {task.goal}\n\n"
            f"{task.result or task.error or ''}",
            title="AEIOS Task",
            border_style=style,
        )
    )
    if task.plan:
        console.print("[dim]plan:[/dim] " + " → ".join(task.plan))
    raise typer.Exit(code=0 if task.status.value == "completed" else 1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8080, help="Bind port"),
    reload: bool = typer.Option(False, help="Auto-reload (dev)"),
) -> None:
    """Start the FastAPI control plane."""
    try:
        import uvicorn
    except ImportError as exc:
        console.print(
            "[red]FastAPI extra not installed.[/red] Run: pip install -e '.[api]'"
        )
        raise typer.Exit(1) from exc

    console.print(f"Starting AEIOS API on http://{host}:{port}")
    uvicorn.run(
        "aeios.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


@app.command("agents")
def list_agents() -> None:
    """List registered agents."""
    k = _kernel()
    for name in k.syscalls.list_agents():
        console.print(f"- {name}")


@app.command("tools")
def list_tools() -> None:
    """List registered tools."""
    k = _kernel()
    for name in k.syscalls.list_tools():
        console.print(f"- {name}")


@task_app.command("list")
def task_list(limit: int = typer.Option(20, help="Max rows")) -> None:
    """List recent persisted tasks."""
    tasks = _kernel().syscalls.list_tasks(limit=limit)
    table = Table(title="Tasks")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Agent")
    table.add_column("Goal")
    for t in tasks:
        table.add_row(t.id, t.status.value, t.agent or "", t.goal[:60])
    console.print(table)


@task_app.command("get")
def task_get(task_id: str = typer.Argument(..., help="Task id")) -> None:
    """Show one persisted task."""
    task = _kernel().syscalls.get_task(task_id)
    if not task:
        console.print(f"[red]Task not found:[/red] {task_id}")
        raise typer.Exit(1)
    console.print_json(task.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
