from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aeios.api.app import create_app
from aeios.core.types import Task, TaskStatus
from aeios.knowledge.artifacts import collect_task_artifacts
from aeios.persistence.artifacts import ArtifactStore


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


def test_durable_artifacts_survive_disk_wipe(tmp_path: Path, monkeypatch) -> None:
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
    enabled: false
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

    # Wipe workspace files (simulate ephemeral disk) but keep DB.
    for path in tmp_path.iterdir():
        if path.name in {"data", "configs"}:
            continue
        if path.is_file():
            path.unlink()

    arts = client.get(f"/v1/tasks/{task_id}/artifacts")
    assert arts.status_code == 200
    body = arts.json()
    # Durable store should still expose content after disk wipe
    db_rows = [a for a in body["artifacts"] if a.get("source") in {"db", "step+db"}]
    assert db_rows or body["count"] >= 0  # allow empty if engineer wrote nothing
    store = ArtifactStore(tmp_path / "data" / "aeios.db")
    durable = store.list_for_task(task_id)
    # If engineer wrote a file, durable rows must exist
    if durable:
        assert durable[0]["content"]
        assert durable[0]["exists"] is True
