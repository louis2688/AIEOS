"""Regression tests for SoftwareEngineer / Architect plan→act→observe paths."""

from __future__ import annotations

from pathlib import Path

import httpx

from aeios.core.kernel import Kernel
from aeios.core.types import TaskStatus
from aeios.planning.planner import Planner
from aeios.tools.http import HttpTool


def _write_config(
    tmp_path: Path,
    *,
    http: bool = True,
    shell: bool = True,
    allow_write: bool = False,
) -> None:
    (tmp_path / "configs").mkdir(exist_ok=True)
    http_block = (
        """
  http:
    enabled: true
    timeout_sec: 5
    max_bytes: 65536
"""
        if http
        else """
  http:
    enabled: false
"""
    )
    shell_block = (
        """
  shell:
    enabled: true
    timeout_sec: 10
"""
        if shell
        else """
  shell:
    enabled: false
"""
    )
    (tmp_path / "configs" / "default.yaml").write_text(
        f"""
kernel:
  default_agent: software_engineer
  max_tool_retries: 1
memory:
  data_dir: ./data
tools:
  filesystem:
    enabled: true
    allow_write: {"true" if allow_write else "false"}
{shell_block}
{http_block}
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


def test_http_tool_registers_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=True)
    kernel = Kernel(workspace=tmp_path)
    assert "http" in kernel.tools
    doctor = kernel.doctor()
    http_check = next(c for c in doctor["checks"] if c["name"] == "http_tool")
    assert http_check["ok"] is True


def test_http_tool_absent_when_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=False)
    kernel = Kernel(workspace=tmp_path)
    assert "http" not in kernel.tools


def test_software_engineer_http_observe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=True, shell=False)
    (tmp_path / "readme.txt").write_text("hello workspace", encoding="utf-8")

    kernel = Kernel(workspace=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="remote payload")

    kernel.register_tool(HttpTool(transport=httpx.MockTransport(handler)))

    task = kernel.run_goal("fetch https://example.test/data and inspect")
    assert task.status == TaskStatus.COMPLETED
    steps = {s["step"]: s for s in task.steps}
    assert "list_workspace" in steps
    assert "http_fetch" in steps
    assert steps["http_fetch"]["status"] == "ok"
    assert task.result is not None
    assert "Observations:" in task.result
    assert "http 200" in task.result


def test_software_engineer_reads_named_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=False, shell=False)
    (tmp_path / "notes.md").write_text("# notes\nline", encoding="utf-8")

    kernel = Kernel(workspace=tmp_path)
    task = kernel.run_goal("review notes.md for structure")
    assert task.status == TaskStatus.COMPLETED
    steps = {s["step"]: s for s in task.steps}
    assert steps.get("read_file", {}).get("status") == "ok"
    assert "read notes.md" in (task.result or "")


def test_architect_grounds_outline_in_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=False, shell=False)
    (tmp_path / "src").mkdir()
    (tmp_path / "apps").mkdir()
    (tmp_path / "configs").mkdir(exist_ok=True)

    kernel = Kernel(workspace=tmp_path)
    task = kernel.run_goal("design module boundaries", agent="architect")
    assert task.status == TaskStatus.COMPLETED
    steps = {s["step"]: s for s in task.steps}
    assert steps["inspect_workspace"]["status"] == "ok"
    outline = steps["architecture_outline"]["output"]
    assert "src" in outline["modules"] or "apps" in outline["modules"]
    assert task.result is not None
    assert "Observations:" in task.result


def test_architect_http_reference(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=True, shell=False)

    kernel = Kernel(workspace=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="OpenAPI docs stub")

    kernel.register_tool(HttpTool(transport=httpx.MockTransport(handler)))

    task = kernel.run_goal(
        "outline architecture using https://example.test/openapi.json",
        agent="architect",
    )
    assert task.status == TaskStatus.COMPLETED
    steps = {s["step"]: s for s in task.steps}
    assert steps["http_reference"]["status"] == "ok"
    assert "fetched reference" in (task.result or "")


def test_planner_http_deterministic_path() -> None:
    planner = Planner()
    plan = planner.deterministic_plan("fetch https://example.com/api")
    assert any("HTTP" in s or "http" in s.lower() for s in plan)

    arch = planner.deterministic_plan(
        "review https://example.com/docs",
        agent_role="architect",
    )
    assert any("HTTP" in s or "Fetch" in s for s in arch)


def test_hello_path_still_works(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=True, shell=True)
    kernel = Kernel(workspace=tmp_path)
    task = kernel.run_goal("hello")
    assert task.status == TaskStatus.COMPLETED
    assert task.result is not None
    assert "AEIOS" in task.result


def test_software_engineer_writes_file_in_jail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=False, shell=False, allow_write=True)

    kernel = Kernel(workspace=tmp_path)
    task = kernel.run_goal("implement create hello_stub.py with a main function")
    assert task.status == TaskStatus.COMPLETED
    steps = {s["step"]: s for s in task.steps}
    assert steps["write_file"]["status"] == "ok"
    assert steps["write_file"].get("observation")
    assert (tmp_path / "hello_stub.py").is_file()
    body = (tmp_path / "hello_stub.py").read_text(encoding="utf-8")
    assert "def main" in body
    assert "Observations:" in (task.result or "")
    assert "write file" in (task.result or "").lower() or "hello_stub.py" in (task.result or "")


def test_software_engineer_updates_existing_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=False, shell=False, allow_write=True)
    (tmp_path / "notes.md").write_text("# notes\n", encoding="utf-8")

    kernel = Kernel(workspace=tmp_path)
    task = kernel.run_goal("edit notes.md to clarify structure")
    assert task.status == TaskStatus.COMPLETED
    steps = {s["step"]: s for s in task.steps}
    assert steps["update_file"]["status"] == "ok"
    assert "AEIOS update" in (tmp_path / "notes.md").read_text(encoding="utf-8")


def test_architect_writes_architecture_md(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, http=False, shell=False, allow_write=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()

    kernel = Kernel(workspace=tmp_path)
    task = kernel.run_goal("outline architecture for billing modules", agent="architect")
    assert task.status == TaskStatus.COMPLETED
    steps = {s["step"]: s for s in task.steps}
    assert steps["architecture_outline"]["status"] == "ok"
    assert steps["architecture_outline"].get("observation")
    assert steps["write_architecture_doc"]["status"] == "ok"
    arch = tmp_path / "docs" / "ARCHITECTURE.md"
    assert arch.is_file()
    text = arch.read_text(encoding="utf-8")
    assert "# Architecture outline" in text
    assert "billing" in text.lower()
    assert "Observations:" in (task.result or "")


def test_planner_implement_deterministic_path() -> None:
    planner = Planner()
    plan = planner.deterministic_plan("implement create app.py")
    assert any("write" in s.lower() or "update" in s.lower() for s in plan)

    arch = planner.deterministic_plan(
        "outline architecture for auth",
        agent_role="architect",
    )
    assert any("ARCHITECTURE" in s or "architecture" in s.lower() for s in arch)
