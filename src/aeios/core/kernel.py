from __future__ import annotations

from pathlib import Path
from typing import Any

from aeios.agents.architect import ArchitectAgent
from aeios.agents.base import BaseAgent
from aeios.agents.echo import EchoAgent
from aeios.agents.software_engineer import SoftwareEngineerAgent
from aeios.config import Settings, get_settings
from aeios.core.scheduler import Scheduler
from aeios.core.syscalls import Syscalls
from aeios.core.types import Task, TaskStatus, ToolResult
from aeios.memory.store import MemoryStore
from aeios.tools.base import BaseTool
from aeios.tools.echo import EchoTool
from aeios.tools.filesystem import FilesystemTool


class Kernel:
    """AEIOS kernel: registry + scheduler + syscall surface."""

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
        self.memory = MemoryStore(data_dir=data_dir)

        kernel_cfg = self.yaml.get("kernel", {})
        self.scheduler = Scheduler(
            max_concurrent=int(kernel_cfg.get("max_concurrent_tasks", 2))
        )
        self.default_agent = str(kernel_cfg.get("default_agent", "software_engineer"))

        self.tools: dict[str, BaseTool] = {}
        self.agents: dict[str, BaseAgent] = {}
        self.tasks: dict[str, Task] = {}
        self.syscalls = Syscalls(self)

        self._register_default_tools()
        self._register_default_agents()

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

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self.tools.get(name)
        if not tool:
            return ToolResult(ok=False, error=f"Unknown tool: {name}")
        try:
            return tool.run(**kwargs)
        except Exception as exc:  # noqa: BLE001 — boundary; surface as ToolResult
            return ToolResult(ok=False, error=str(exc))

    def run_goal(self, goal: str, agent: str | None = None) -> Task:
        agent_name = agent or self.default_agent
        if agent_name not in self.agents:
            task = Task(goal=goal, status=TaskStatus.FAILED, agent=agent_name)
            task.error = f"Unknown agent: {agent_name}"
            self.tasks[task.id] = task
            return task

        task = Task(goal=goal, status=TaskStatus.PLANNING, agent=agent_name)
        self.tasks[task.id] = task
        self.scheduler.enqueue(task)

        def worker(queued: Task) -> None:
            runner = self.agents[agent_name]
            finished = runner.execute(queued)
            self.tasks[finished.id] = finished
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
        return self.tasks[task.id]

    def status(self) -> dict[str, Any]:
        return {
            "version": "0.1.0",
            "env": self.settings.aeios_env,
            "workspace": str(self.workspace),
            "agents": sorted(self.agents.keys()),
            "tools": sorted(self.tools.keys()),
            "scheduler": {
                "pending": self.scheduler.pending,
                "active": self.scheduler.active,
            },
            "memory_keys": self.memory.keys(),
            "tasks_tracked": len(self.tasks),
            "last_task_id": self.memory.get("last_task_id"),
        }
