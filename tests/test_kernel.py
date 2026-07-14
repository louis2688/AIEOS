from pathlib import Path

from aeios.core.kernel import Kernel
from aeios.core.types import TaskStatus


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
