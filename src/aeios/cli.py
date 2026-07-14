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
    for key in ("version", "env", "workspace", "tasks_tracked", "last_task_id"):
        table.add_row(key, str(info.get(key)))
    table.add_row("agents", ", ".join(info["agents"]))
    table.add_row("tools", ", ".join(info["tools"]))
    table.add_row(
        "scheduler",
        f"pending={info['scheduler']['pending']} active={info['scheduler']['active']}",
    )
    console.print(table)


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


if __name__ == "__main__":
    app()
