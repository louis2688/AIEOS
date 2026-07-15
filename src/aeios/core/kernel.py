from __future__ import annotations

from pathlib import Path
from typing import Any

from aeios import __version__
from aeios.agents.architect import ArchitectAgent
from aeios.agents.base import BaseAgent
from aeios.agents.echo import EchoAgent
from aeios.agents.software_engineer import SoftwareEngineerAgent
from aeios.config import Settings, get_settings
from aeios.core.scheduler import Scheduler
from aeios.core.state_machine import InvalidTransition, transition
from aeios.core.syscalls import Syscalls
from aeios.core.types import Task, TaskStatus, ToolResult
from aeios.memory.store import MemoryStore
from aeios.persistence.models import ModelStore
from aeios.persistence.sqlite_store import SqliteTaskStore
from aeios.planning.planner import Planner
from aeios.tools.base import BaseTool
from aeios.tools.echo import EchoTool
from aeios.tools.filesystem import FilesystemTool
from aeios.tools.shell import ShellTool


class Kernel:
    """AEIOS kernel: registry + scheduler + persistence + syscall surface."""

    def __init__(
        self,
        settings: Settings | None = None,
        workspace: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.yaml = self.settings.load_yaml()
        self.workspace = (workspace or Path.cwd()).resolve()

        mem_cfg = self.yaml.get("memory", {})
        data_dir = Path(mem_cfg.get("data_dir", "./data"))
        if not data_dir.is_absolute():
            data_dir = self.workspace / data_dir
        self.data_dir = data_dir
        self.memory = MemoryStore(data_dir=data_dir)

        db_path = self._resolve_sqlite_path(
            self.settings.database_url, data_dir, self.workspace
        )
        self.store = SqliteTaskStore(db_path)
        self.models = ModelStore(db_path)
        self.models.seed_from_env(
            openai_api_key=self.settings.openai_api_key,
            anthropic_api_key=self.settings.anthropic_api_key,
        )

        kernel_cfg = self.yaml.get("kernel", {})
        self.scheduler = Scheduler(
            max_concurrent=int(kernel_cfg.get("max_concurrent_tasks", 2))
        )
        self.default_agent = str(kernel_cfg.get("default_agent", "software_engineer"))
        self.planner = Planner(self.settings, model_store=self.models)

        self.tools: dict[str, BaseTool] = {}
        self.agents: dict[str, BaseAgent] = {}
        self.tasks: dict[str, Task] = {}
        self.syscalls = Syscalls(self)

        self._register_default_tools()
        self._register_default_agents()
        self.store.audit("kernel_boot", detail={"workspace": str(self.workspace)})

    @staticmethod
    def _resolve_sqlite_path(database_url: str, data_dir: Path, workspace: Path) -> Path:
        if database_url.startswith("sqlite:///"):
            raw = database_url.removeprefix("sqlite:///")
            path = Path(raw)
            if not path.is_absolute():
                path = workspace / path
            return path
        # Non-sqlite URLs fall back to local file until Postgres lands
        return data_dir / "aeios.db"

    def _register_default_tools(self) -> None:
        tools_cfg = self.yaml.get("tools", {})
        self.register_tool(EchoTool())

        fs_cfg = tools_cfg.get("filesystem", {})
        if fs_cfg.get("enabled", True):
            self.register_tool(
                FilesystemTool(
                    root=self.workspace,
                    allow_write=bool(fs_cfg.get("allow_write", False)),
                )
            )

        shell_cfg = tools_cfg.get("shell", {})
        if shell_cfg.get("enabled", False):
            allow = shell_cfg.get("allowlist")
            self.register_tool(
                ShellTool(
                    root=self.workspace,
                    allowlist=set(allow) if allow else None,
                    timeout_sec=float(shell_cfg.get("timeout_sec", 15)),
                )
            )

    def _register_default_agents(self) -> None:
        agents_cfg = self.yaml.get("agents", {})
        catalog: list[type[BaseAgent]] = [
            EchoAgent,
            SoftwareEngineerAgent,
            ArchitectAgent,
        ]
        for cls in catalog:
            enabled = agents_cfg.get(cls.name, {}).get("enabled", True)
            if enabled:
                self.register_agent(cls(self))

    def register_tool(self, tool: BaseTool) -> None:
        self.tools[tool.name] = tool

    def register_agent(self, agent: BaseAgent) -> None:
        self.agents[agent.name] = agent

    def set_task_status(self, task: Task, status: TaskStatus) -> Task:
        try:
            task.status = transition(task.status, status)
        except InvalidTransition as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
        task.touch()
        self._persist(task, event=f"status:{task.status.value}")
        return task

    def _persist(self, task: Task, event: str | None = None) -> None:
        self.tasks[task.id] = task
        self.store.save_task(task)
        if event:
            self.store.audit(event, task_id=task.id, detail={"status": task.status.value})

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self.tools.get(name)
        if not tool:
            return ToolResult(ok=False, error=f"Unknown tool: {name}")
        try:
            result = tool.run(**kwargs)
        except Exception as exc:  # noqa: BLE001 — boundary; surface as ToolResult
            result = ToolResult(ok=False, error=str(exc))
        self.store.audit(
            "call_tool",
            detail={"tool": name, "ok": result.ok, "error": result.error},
        )
        return result

    def get_task(self, task_id: str) -> Task | None:
        if task_id in self.tasks:
            return self.tasks[task_id]
        return self.store.get_task(task_id)

    def list_tasks(self, limit: int = 50) -> list[Task]:
        return self.store.list_tasks(limit=limit)

    def run_goal(self, goal: str, agent: str | None = None) -> Task:
        agent_name = agent or self.default_agent
        if agent_name not in self.agents:
            task = Task(goal=goal, status=TaskStatus.FAILED, agent=agent_name)
            task.error = f"Unknown agent: {agent_name}"
            self._persist(task, event="task_failed_unknown_agent")
            return task

        task = Task(goal=goal, status=TaskStatus.PENDING, agent=agent_name)
        self._persist(task, event="task_created")
        self.set_task_status(task, TaskStatus.PLANNING)
        self.scheduler.enqueue(task)

        def worker(queued: Task) -> None:
            self.set_task_status(queued, TaskStatus.RUNNING)
            runner = self.agents[agent_name]
            finished = runner.execute(queued)
            # Agents may already set completed/failed; normalize if still running
            if finished.status == TaskStatus.RUNNING:
                self.set_task_status(finished, TaskStatus.COMPLETED)
            else:
                self._persist(finished, event=f"task_{finished.status.value}")

            self.memory.append_history(
                {
                    "id": finished.id,
                    "goal": finished.goal,
                    "agent": finished.agent,
                    "status": finished.status.value,
                    "result": finished.result,
                    "error": finished.error,
                }
            )
            self.memory.set("last_task_id", finished.id)

        self.scheduler.drain(worker)
        return self.get_task(task.id) or task

    def status(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "env": self.settings.aeios_env,
            "workspace": str(self.workspace),
            "agents": sorted(self.agents.keys()),
            "tools": sorted(self.tools.keys()),
            "scheduler": {
                "pending": self.scheduler.pending,
                "active": self.scheduler.active,
            },
            "memory_keys": self.memory.keys(),
            "tasks_tracked": len(self.list_tasks(limit=1000)),
            "last_task_id": self.memory.get("last_task_id"),
            "db_path": str(self.store.db_path),
            "llm_planner": bool(self.models.get_default() or self.settings.openai_api_key),
            "default_model": (
                {
                    "id": m.id,
                    "name": m.name,
                    "provider": m.provider,
                    "model_id": m.model_id,
                }
                if (m := self.models.get_default())
                else None
            ),
            "models_count": len(self.models.list(limit=1000)),
        }

    def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "ok": ok, "detail": detail})

        add("workspace", self.workspace.exists(), str(self.workspace))
        add("config", self.settings.config_path.exists(), str(self.settings.config_path))
        add("sqlite", self.store.healthy(), str(self.store.db_path))
        add("agents", len(self.agents) > 0, f"{len(self.agents)} registered")
        add("tools", len(self.tools) > 0, f"{len(self.tools)} registered")
        add(
            "shell_tool",
            "shell" in self.tools,
            "enabled" if "shell" in self.tools else "disabled (enable in configs/default.yaml)",
        )
        default = self.models.get_default()
        add(
            "model_library",
            default is not None or bool(self.settings.openai_api_key),
            (
                f"{default.provider}/{default.model_id}"
                if default
                else (
                    "env openai fallback"
                    if self.settings.openai_api_key
                    else "empty (deterministic planner)"
                )
            ),
        )

        # Optional live probe for Qdrant — soft check
        qdrant_ok = False
        qdrant_detail = self.settings.qdrant_url
        try:
            import httpx

            r = httpx.get(f"{self.settings.qdrant_url.rstrip('/')}/readyz", timeout=1.5)
            qdrant_ok = r.status_code < 500
            qdrant_detail = f"{self.settings.qdrant_url} → {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            qdrant_detail = f"{self.settings.qdrant_url} unreachable ({exc.__class__.__name__})"
        add("qdrant", qdrant_ok, qdrant_detail)

        return {
            "ok": all(
                c["ok"]
                for c in checks
                if c["name"] not in {"qdrant", "model_library"}
            ),
            "checks": checks,
        }
