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
from aeios.knowledge.vectors import QdrantKnowledgeIndex, try_open_qdrant
from aeios.memory.store import MemoryStore
from aeios.persistence.artifacts import ArtifactStore
from aeios.persistence.db import open_db
from aeios.persistence.models import ModelStore
from aeios.persistence.sqlite_store import SqliteTaskStore
from aeios.planning.planner import Planner
from aeios.tools.base import BaseTool
from aeios.tools.mcp import McpBridge, load_mcp_tools


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

        self.db = open_db(
            self.settings.database_url,
            workspace=self.workspace,
            data_dir=data_dir,
        )
        self.store = SqliteTaskStore(self.db)
        self.artifacts = ArtifactStore(self.db)
        self.models = ModelStore(self.db, settings=self.settings)
        self.models.seed_from_env(
            openai_api_key=self.settings.openai_api_key,
            anthropic_api_key=self.settings.anthropic_api_key,
        )

        mem_backend = str(mem_cfg.get("backend", "local")).lower()
        qdrant_wanted = self.settings.qdrant_enabled and mem_backend in {
            "local",
            "qdrant",
            "sqlite",
        }
        self.vector_index: QdrantKnowledgeIndex | None = try_open_qdrant(
            self.settings.qdrant_url,
            collection=self.settings.qdrant_collection,
            enabled=qdrant_wanted,
        )

        kernel_cfg = self.yaml.get("kernel", {})
        self.scheduler = Scheduler(
            max_concurrent=int(kernel_cfg.get("max_concurrent_tasks", 2))
        )
        self.default_agent = str(kernel_cfg.get("default_agent", "software_engineer"))
        self.max_tool_retries = int(
            kernel_cfg.get("max_tool_retries", self.settings.max_tool_retries)
        )
        self.planner = Planner(self.settings, model_store=self.models)

        self.tools: dict[str, BaseTool] = {}
        self.agents: dict[str, BaseAgent] = {}
        self.tasks: dict[str, Task] = {}
        self._active_task: Task | None = None
        self._cancel_requested: set[str] = set()
        self._mcp_bridge: McpBridge | None = None
        self.syscalls = Syscalls(self)

        self._register_default_tools()
        self._register_default_agents()
        self.store.audit("kernel_boot", detail={"workspace": str(self.workspace)})

    def _register_default_tools(self) -> None:
        # Lazy imports avoid tools ↔ core circular import at module load time.
        from aeios.tools.echo import EchoTool
        from aeios.tools.filesystem import FilesystemTool
        from aeios.tools.http import HttpTool
        from aeios.tools.shell import ShellTool

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

        http_cfg = tools_cfg.get("http", {})
        if http_cfg.get("enabled", False):
            self.register_tool(
                HttpTool(
                    timeout_sec=float(http_cfg.get("timeout_sec", 15)),
                    max_bytes=int(http_cfg.get("max_bytes", 1_048_576)),
                )
            )

        # External MCP tools — optional; agents still use call_tool only.
        self._register_mcp_tools(tools_cfg.get("mcp"))

    def _register_mcp_tools(self, mcp_cfg: dict[str, Any] | None) -> None:
        """Register MCP-backed tools when servers are configured.

        No servers / disabled → no-op. Connect failures are soft (logged + audited).
        """
        tools, bridge = load_mcp_tools(mcp_cfg)
        self._mcp_bridge = bridge
        for tool in tools:
            self.register_tool(tool)
        if bridge is not None:
            self.store.audit(
                "mcp_bridge",
                detail={
                    "servers": [s.name for s in bridge.servers],
                    "tools": [t.name for t in tools],
                    "errors": list(bridge.errors),
                },
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

    def _invoke_tool(self, name: str, **kwargs: Any) -> ToolResult:
        from aeios.observability.metrics import get_metrics

        tool = self.tools.get(name)
        if not tool:
            result = ToolResult(ok=False, error=f"Unknown tool: {name}")
            get_metrics().record_tool_call(name, ok=False)
            return result
        try:
            result = tool.run(**kwargs)
        except Exception as exc:  # noqa: BLE001 — boundary; surface as ToolResult
            result = ToolResult(ok=False, error=str(exc))
        get_metrics().record_tool_call(name, ok=result.ok)
        return result

    def is_cancel_requested(self, task_id: str) -> bool:
        return task_id in self._cancel_requested

    def request_cancel(self, task_id: str) -> Task | None:
        """Request cancellation of an in-flight or queued task."""
        task = self.get_task(task_id)
        if not task:
            return None
        if task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            return task
        self._cancel_requested.add(task_id)
        if task.status in {
            TaskStatus.PENDING,
            TaskStatus.PLANNING,
            TaskStatus.RUNNING,
        }:
            task.error = task.error or "Cancelled by user"
            self.set_task_status(task, TaskStatus.CANCELLED)
        return self.get_task(task_id) or task

    def _apply_cancel_if_requested(self, task: Task) -> bool:
        if task.id not in self._cancel_requested:
            return False
        if task.status != TaskStatus.CANCELLED:
            task.error = task.error or "Cancelled by user"
            self.set_task_status(task, TaskStatus.CANCELLED)
        return True

    def _persist_filesystem_artifact(
        self, task: Task, result: ToolResult, kwargs: dict[str, Any]
    ) -> None:
        if not result.ok:
            return
        action = str(kwargs.get("action") or "").lower()
        if action not in {"write", "update"}:
            return
        path = kwargs.get("path")
        content = kwargs.get("content")
        if not isinstance(path, str) or not path.strip():
            return
        if content is None:
            # Prefer tool output payload when content not in kwargs
            out = result.output
            if isinstance(out, dict) and isinstance(out.get("content"), str):
                content = out["content"]
            else:
                return
        try:
            self.artifacts.upsert(
                task_id=task.id,
                path=path,
                content=str(content),
                owner_id=task.owner_id or "local",
            )
        except Exception:  # noqa: BLE001 — persistence must not break tools
            self.store.audit(
                "artifact_persist_failed",
                task_id=task.id,
                detail={"path": path},
            )

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        """Invoke a tool with a bounded reflection/retry loop on failure."""
        task = self._active_task
        task_id = task.id if task else None
        if task is not None and self._apply_cancel_if_requested(task):
            return ToolResult(ok=False, error="Task cancelled")
        max_retries = max(0, self.max_tool_retries)
        unknown = name not in self.tools
        attempts = 0

        while True:
            if task is not None and self._apply_cancel_if_requested(task):
                return ToolResult(ok=False, error="Task cancelled")
            result = self._invoke_tool(name, **kwargs)
            attempts += 1
            self.store.audit(
                "call_tool",
                task_id=task_id,
                detail={
                    "tool": name,
                    "ok": result.ok,
                    "error": result.error,
                    "attempt": attempts,
                },
            )
            if result.ok and name == "filesystem" and task is not None:
                self._persist_filesystem_artifact(task, result, kwargs)
            if result.ok or unknown or attempts > max_retries:
                return result

            # Tool failed with retries remaining — reflect, re-plan, retry.
            retry_num = attempts  # 1-based failure count before this retry
            reflection, revised_plan = self.planner.reflect(
                goal=task.goal if task else "",
                tool=name,
                error=result.error or "unknown error",
                attempt=retry_num,
                agent_role=(task.agent or self.default_agent)
                if task
                else self.default_agent,
            )
            if task is not None:
                task.plan = revised_plan
                task.steps.append(
                    {
                        "step": "reflection",
                        "status": "retry",
                        "tool": name,
                        "attempt": retry_num,
                        "error": result.error,
                        "reflection": reflection,
                        "revised_plan": revised_plan,
                    }
                )
                task.touch()
                self._persist(task)
            self.store.audit(
                "tool_retry",
                task_id=task_id,
                detail={
                    "tool": name,
                    "attempt": retry_num,
                    "max_retries": max_retries,
                    "error": result.error,
                    "reflection": reflection,
                },
            )

    def get_task(
        self, task_id: str, *, owner_id: str | None = None
    ) -> Task | None:
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if owner_id is not None and (task.owner_id or "local") != owner_id:
                return None
            return task
        return self.store.get_task(task_id, owner_id=owner_id)

    def list_tasks(
        self, limit: int = 50, *, owner_id: str | None = None
    ) -> list[Task]:
        return self.store.list_tasks(limit=limit, owner_id=owner_id)

    def run_goal(
        self, goal: str, agent: str | None = None, *, owner_id: str = "local"
    ) -> Task:
        """Create and run a goal synchronously (blocks until finished)."""
        task = self._prepare_task(goal, agent, owner_id=owner_id)
        if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            self._record_task_finished(ok=False)
            return task
        self.scheduler.enqueue(task)
        self.scheduler.drain(lambda queued: self._execute_queued(queued))
        return self.get_task(task.id) or task

    def run_goal_async(
        self, goal: str, agent: str | None = None, *, owner_id: str = "local"
    ) -> Task:
        """Create a task and execute it on a daemon thread; return immediately."""
        import threading

        task = self._prepare_task(goal, agent, owner_id=owner_id)
        if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            self._record_task_finished(ok=False)
            return task
        self.scheduler.enqueue(task)

        def _bg() -> None:
            self.scheduler.drain(lambda queued: self._execute_queued(queued))

        threading.Thread(target=_bg, name=f"aeios-task-{task.id[:8]}", daemon=True).start()
        return task

    @staticmethod
    def _record_task_finished(*, ok: bool) -> None:
        try:
            from aeios.observability.metrics import get_metrics

            get_metrics().record_task_finished(ok=ok)
        except Exception:  # noqa: BLE001
            pass

    def _prepare_task(
        self,
        goal: str,
        agent: str | None = None,
        *,
        owner_id: str = "local",
    ) -> Task:
        agent_name = agent or self.default_agent
        owner = (owner_id or "local").strip() or "local"
        if agent_name not in self.agents:
            task = Task(
                goal=goal,
                status=TaskStatus.FAILED,
                agent=agent_name,
                owner_id=owner,
            )
            task.error = f"Unknown agent: {agent_name}"
            self._persist(task, event="task_failed_unknown_agent")
            return task

        task = Task(
            goal=goal,
            status=TaskStatus.PENDING,
            agent=agent_name,
            owner_id=owner,
        )
        self._persist(task, event="task_created")
        self.set_task_status(task, TaskStatus.PLANNING)
        return task

    def _execute_queued(self, queued: Task) -> None:
        if self._apply_cancel_if_requested(queued):
            self._cancel_requested.discard(queued.id)
            self._record_task_finished(ok=False)
            return
        agent_name = queued.agent or self.default_agent
        self.set_task_status(queued, TaskStatus.RUNNING)
        if self._apply_cancel_if_requested(queued):
            self._cancel_requested.discard(queued.id)
            self._record_task_finished(ok=False)
            return
        runner = self.agents[agent_name]
        self._active_task = queued
        try:
            finished = runner.execute(queued)
        finally:
            self._active_task = None
        # Prefer cancel flag over agent-assigned terminal status (agents set
        # status fields directly and can race a cancel request).
        if finished.id in self._cancel_requested:
            finished.status = TaskStatus.CANCELLED
            finished.error = finished.error or "Cancelled by user"
            finished.touch()
            self._persist(finished, event="status:cancelled")
        elif finished.status == TaskStatus.RUNNING:
            self.set_task_status(finished, TaskStatus.COMPLETED)
        else:
            self._persist(finished, event=f"task_{finished.status.value}")

        self._cancel_requested.discard(finished.id)
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
        self._record_task_finished(ok=finished.status == TaskStatus.COMPLETED)

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
            "db_path": self.db.display,
            "db_backend": self.db.backend,
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
        db_ok = self.store.healthy()
        if self.db.backend == "postgres":
            add("postgres", db_ok, self.db.display)
            add("sqlite", True, "skipped (DATABASE_URL is postgres)")
        else:
            add("sqlite", db_ok, self.db.display)
            add("postgres", True, "skipped (using sqlite; set DATABASE_URL=postgresql://…)")
        add("agents", len(self.agents) > 0, f"{len(self.agents)} registered")
        add("tools", len(self.tools) > 0, f"{len(self.tools)} registered")
        add(
            "shell_tool",
            "shell" in self.tools,
            "enabled" if "shell" in self.tools else "disabled (enable in configs/default.yaml)",
        )
        add(
            "http_tool",
            "http" in self.tools,
            "enabled" if "http" in self.tools else "disabled (enable in configs/default.yaml)",
        )
        mcp_tools = [n for n in self.tools if n.startswith("mcp_")]
        mcp_cfg = self.yaml.get("tools", {}).get("mcp") or {}
        mcp_servers = mcp_cfg.get("servers") or []
        if mcp_servers:
            mcp_ok = len(mcp_tools) > 0 or (
                self._mcp_bridge is not None and not self._mcp_bridge.errors
            )
            mcp_detail = (
                f"{len(mcp_tools)} tool(s) from {len(mcp_servers)} server(s)"
                if mcp_tools
                else (
                    "; ".join(self._mcp_bridge.errors)
                    if self._mcp_bridge and self._mcp_bridge.errors
                    else "configured but no tools discovered"
                )
            )
            add("mcp_bridge", mcp_ok, mcp_detail)
        else:
            add("mcp_bridge", True, "disabled (no servers in configs/default.yaml)")
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

        # Optional live probe for Qdrant — soft check (never fails doctor ok)
        qdrant_ok = False
        qdrant_detail = self.settings.qdrant_url
        if self.vector_index is not None:
            st = self.vector_index.status()
            qdrant_ok = bool(st.get("ok"))
            qdrant_detail = (
                f"{st.get('url')} collection={st.get('collection')} ({st.get('detail')})"
            )
        else:
            try:
                import httpx

                r = httpx.get(
                    f"{self.settings.qdrant_url.rstrip('/')}/readyz", timeout=1.5
                )
                qdrant_ok = r.status_code < 500
                qdrant_detail = f"{self.settings.qdrant_url} → {r.status_code}"
            except Exception as exc:  # noqa: BLE001
                qdrant_detail = (
                    f"{self.settings.qdrant_url} unreachable ({exc.__class__.__name__})"
                )
        add("qdrant", qdrant_ok, qdrant_detail)

        soft = {"qdrant", "model_library", "mcp_bridge"}
        if self.db.backend == "postgres":
            soft.add("sqlite")
        else:
            soft.add("postgres")

        return {
            "ok": all(c["ok"] for c in checks if c["name"] not in soft),
            "checks": checks,
        }
