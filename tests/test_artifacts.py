from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.core.types import Task, TaskStatus
from aeios.knowledge.artifacts import collect_task_artifacts


def test_collect_artifacts_from_step_output(tmp_path: Path) -> None:
    (tmp_path / "OUT.md").write_text("# hi\n", encoding="utf-8")
    task = Task(
        goal="write",
        status=TaskStatus.COMPLETED,
        steps=[
            {
                "tool": "filesystem",
                "status": "ok",
                "output": {"path": "OUT.md", "action": "write", "bytes": 5},
            }
        ],
    )
    arts = collect_task_artifacts(task, tmp_path)
    assert len(arts) == 1
    assert arts[0]["path"] == "OUT.md"
    assert arts[0]["exists"] is True
    assert "hi" in (arts[0]["content"] or "")


def test_artifacts_api_after_engineer_write(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs" / "default.yaml").write_text(
        """
kernel:
  default_agent: software_engineer
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
    allow_write: true
  shell:
    enabled: false
agents:
  software_engineer:
    enabled: true
  echo:
    enabled: true
  architect:
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    client = TestClient(create_app(workspace=tmp_path))
    created = client.post(
        "/v1/tasks",
        json={"goal": "implement a hello stub in HELLO.md", "agent": "software_engineer"},
    )
    assert created.status_code == 200
    task_id = created.json()["id"]
    arts = client.get(f"/v1/tasks/{task_id}/artifacts")
    assert arts.status_code == 200
    body = arts.json()
    assert body["task_id"] == task_id
    # Engineer should have written something; paths may vary
    assert "artifacts" in body
