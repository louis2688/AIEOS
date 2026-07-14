from pathlib import Path

from aeios.core.kernel import Kernel
from aeios.core.state_machine import InvalidTransition, transition
from aeios.core.types import TaskStatus


def _write_config(tmp_path: Path, shell: bool = False) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text(
        f"""
kernel:
  default_agent: software_engineer
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
  shell:
    enabled: {str(shell).lower()}
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


def test_state_machine_allows_happy_path() -> None:
    status = TaskStatus.PENDING
    status = transition(status, TaskStatus.PLANNING)
    status = transition(status, TaskStatus.RUNNING)
    status = transition(status, TaskStatus.COMPLETED)
    assert status == TaskStatus.COMPLETED


def test_state_machine_rejects_illegal() -> None:
    try:
        transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)
        raise AssertionError("expected InvalidTransition")
    except InvalidTransition:
        pass


def test_task_persists_across_kernel_instances(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    k1 = Kernel(workspace=tmp_path)
    task = k1.run_goal("hello")
    assert task.status == TaskStatus.COMPLETED

    k2 = Kernel(workspace=tmp_path)
    loaded = k2.get_task(task.id)
    assert loaded is not None
    assert loaded.goal == "hello"
    assert loaded.status == TaskStatus.COMPLETED
    assert any(t.id == task.id for t in k2.list_tasks())
