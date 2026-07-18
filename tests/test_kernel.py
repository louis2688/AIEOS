from pathlib import Path
from typing import Any

# Import kernel first to avoid agents ↔ core circular import during collection.
from aeios.core.kernel import Kernel
from aeios.core.types import Task, TaskStatus, ToolResult
from aeios.agents.base import BaseAgent
from aeios.tools.base import BaseTool


class FlakyTool(BaseTool):
    """Fails a fixed number of times, then succeeds."""

    name = "flaky"
    description = "test flaky tool"

    def __init__(self, fail_times: int = 1) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def run(self, **_: Any) -> ToolResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            return ToolResult(ok=False, error="transient failure")
        return ToolResult(ok=True, output="recovered")


class FlakyAgent(BaseAgent):
    name = "flaky_agent"
    role = "test"

    def execute(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        result = self.call_tool("flaky")
        task.steps.append(
            {
                "step": "flaky",
                "status": "ok" if result.ok else "error",
                "output": result.output,
                "error": result.error,
            }
        )
        if result.ok:
            task.status = TaskStatus.COMPLETED
            task.result = str(result.output)
        else:
            task.status = TaskStatus.FAILED
            task.error = result.error
        task.touch()
        return task


def _write_minimal_config(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: software_engineer
  max_tool_retries: 2
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
    allow_write: false
agents:
  echo:
    enabled: true
  software_engineer:
    enabled: true
  architect:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_hello_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: software_engineer
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
    allow_write: false
agents:
  echo:
    enabled: true
  software_engineer:
    enabled: true
  architect:
    enabled: true
""".strip(),
        encoding="utf-8",
    )

    kernel = Kernel(workspace=tmp_path)
    task = kernel.run_goal("hello")

    assert task.status == TaskStatus.COMPLETED
    assert task.result is not None
    assert "AEIOS" in task.result
    assert kernel.memory.get("last_task_id") == task.id


def test_syscalls_list_and_memory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "default.yaml").write_text("{}", encoding="utf-8")

    kernel = Kernel(workspace=tmp_path)
    assert "software_engineer" in kernel.syscalls.list_agents()
    assert "echo" in kernel.syscalls.list_tools()

    kernel.syscalls.request_memory("set", "foo", "bar")
    assert kernel.syscalls.request_memory("get", "foo") == "bar"


def test_filesystem_jail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "default.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("ok", encoding="utf-8")

    kernel = Kernel(workspace=tmp_path)
    ok = kernel.call_tool("filesystem", action="read", path="readme.txt")
    assert ok.ok is True
    assert ok.output == "ok"

    bad = kernel.call_tool("filesystem", action="read", path="../outside.txt")
    assert bad.ok is False


def test_tool_retry_succeeds_after_transient_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_config(tmp_path)

    kernel = Kernel(workspace=tmp_path)
    flaky = FlakyTool(fail_times=1)
    kernel.register_tool(flaky)
    kernel.max_tool_retries = 2

    task = Task(goal="recover from flaky tool", agent="flaky_agent")
    kernel._active_task = task
    try:
        result = kernel.call_tool("flaky")
    finally:
        kernel._active_task = None

    assert result.ok is True
    assert result.output == "recovered"
    assert flaky.calls == 2
    retries = [s for s in task.steps if s.get("status") == "retry"]
    assert len(retries) == 1
    assert retries[0]["tool"] == "flaky"
    assert "transient" in (retries[0].get("error") or "")
    assert retries[0].get("reflection")
    assert retries[0].get("revised_plan")

    audit = kernel.store.list_audit(task_id=task.id, limit=50)
    events = [a["event"] for a in audit]
    assert "tool_retry" in events


def test_tool_retry_exhaustion_marks_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_config(tmp_path)

    kernel = Kernel(workspace=tmp_path)
    flaky = FlakyTool(fail_times=100)
    kernel.register_tool(flaky)
    kernel.register_agent(FlakyAgent(kernel))
    kernel.max_tool_retries = 2

    task = kernel.run_goal("always fail", agent="flaky_agent")

    assert task.status == TaskStatus.FAILED
    assert task.error == "transient failure"
    # 1 initial attempt + 2 retries
    assert flaky.calls == 3

    retries = [s for s in task.steps if s.get("status") == "retry"]
    assert len(retries) == 2
    assert [s["attempt"] for s in retries] == [1, 2]

    audit = kernel.store.list_audit(task_id=task.id, limit=50)
    retry_events = [a for a in audit if a["event"] == "tool_retry"]
    assert len(retry_events) == 2
    call_events = [a for a in audit if a["event"] == "call_tool"]
    assert len(call_events) == 3
