"""LLM observe→act→reflect loop (mocked ModelClient — no network)."""

from __future__ import annotations

from pathlib import Path

from aeios.agents.act_loop import _parse_action, try_llm_act
from aeios.core.kernel import Kernel
from aeios.core.types import Task, TaskStatus
from aeios.models.client import ModelClient


def _write_config(tmp_path: Path) -> None:
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
  http:
    enabled: false
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


class _ScriptedClient(ModelClient):
    def __init__(self, replies: list[str]) -> None:
        super().__init__()
        self._replies = list(replies)
        self.calls = 0

    def complete(self, model, *, system: str, user: str, temperature=0.2, timeout=30.0) -> str:
        self.calls += 1
        if not self._replies:
            return '{"action":"done","result":"fallback done"}'
        return self._replies.pop(0)


def test_parse_action_accepts_fenced_json() -> None:
    raw = 'Here:\n```json\n{"action":"done","result":"ok"}\n```'
    assert _parse_action(raw) == {"action": "done", "result": "ok"}


def test_llm_act_loop_writes_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write_config(tmp_path)
    kernel = Kernel(workspace=tmp_path)
    model = kernel.models.create(
        name="Test",
        provider="openai",
        model_id="gpt-test",
        owner_id="local",
        is_default=True,
        api_key=None,
    )
    assert model.id

    client = _ScriptedClient(
        [
            '{"action":"tool","tool":"filesystem","args":{"action":"write","path":"HELLO.md","content":"# hi\\n"}}',
            '{"action":"done","result":"Wrote HELLO.md"}',
        ]
    )
    agent = kernel.agents["software_engineer"]
    task = Task(goal="write HELLO.md", agent="software_engineer", owner_id="local")
    task.plan = ["write file"]
    task.status = TaskStatus.RUNNING

    used = try_llm_act(agent, task, client=client, max_steps=5)
    assert used is True
    assert client.calls == 2
    assert task.status == TaskStatus.COMPLETED
    assert "HELLO.md" in (task.result or "")
    assert (tmp_path / "HELLO.md").read_text(encoding="utf-8").startswith("# hi")
    assert any(s.get("step") == "llm_tool" for s in task.steps)


def test_engineer_uses_heuristic_without_library_model(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write_config(tmp_path)
    kernel = Kernel(workspace=tmp_path)
    assert kernel.models.get_default(owner_id="local") is None
    task = kernel.run_goal("hello", agent="software_engineer")
    assert task.status == TaskStatus.COMPLETED
    assert not any(s.get("step") == "llm_act_start" for s in task.steps)


def test_architect_llm_act_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write_config(tmp_path)
    kernel = Kernel(workspace=tmp_path)
    kernel.models.create(
        name="Test",
        provider="openai",
        model_id="gpt-test",
        owner_id="local",
        is_default=True,
    )
    client = _ScriptedClient(
        [
            '{"action":"tool","tool":"filesystem","args":{"action":"list","path":"."}}',
            (
                '{"action":"tool","tool":"filesystem","args":{"action":"write",'
                '"path":"ARCHITECTURE.md","content":"# Arch\\n"}}'
            ),
            '{"action":"done","result":"Architecture documented"}',
        ]
    )
    agent = kernel.agents["architect"]
    # Inject client via run_with_optional_llm
    task = Task(goal="outline architecture", agent="architect", owner_id="local")
    finished = agent.run_with_optional_llm(
        task, agent._heuristic_execute, client=client, max_steps=6
    )
    assert finished.status == TaskStatus.COMPLETED
    assert any(s.get("step") == "llm_act_start" for s in finished.steps)
    assert (tmp_path / "ARCHITECTURE.md").is_file()


def test_llm_act_respects_cancel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _write_config(tmp_path)
    kernel = Kernel(workspace=tmp_path)
    kernel.models.create(
        name="Test",
        provider="openai",
        model_id="gpt-test",
        owner_id="local",
        is_default=True,
    )

    class _CancelClient(ModelClient):
        def complete(self, model, **kwargs) -> str:
            # Cancel before returning so the loop sees the flag
            kernel._cancel_requested.add(task.id)
            return '{"action":"tool","tool":"echo","args":{"message":"x"}}'

    agent = kernel.agents["software_engineer"]
    task = Task(goal="do stuff", agent="software_engineer", owner_id="local")
    task.status = TaskStatus.RUNNING
    task.plan = ["work"]
    # Pre-set cancel so first iteration exits before LLM
    kernel._cancel_requested.add(task.id)
    used = try_llm_act(agent, task, client=_CancelClient(), max_steps=3)
    assert used is True
    assert task.status == TaskStatus.CANCELLED
