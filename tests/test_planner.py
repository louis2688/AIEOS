from unittest.mock import MagicMock

from aeios.persistence.models import ModelRecord
from aeios.planning.planner import Planner


def test_deterministic_hello_plan() -> None:
    planner = Planner()
    plan = planner.deterministic_plan("hello")
    assert "Call echo tool" in plan


def test_architect_plan() -> None:
    planner = Planner()
    plan = planner.deterministic_plan("design billing", agent_role="architect")
    assert any("module" in s.lower() or "boundar" in s.lower() for s in plan)


def test_parse_steps_json() -> None:
    steps = Planner._parse_steps('["a", "b", "c"]')
    assert steps == ["a", "b", "c"]


def test_plan_uses_model_library_default() -> None:
    store = MagicMock()
    store.get_default.return_value = ModelRecord(
        id="m1",
        name="Test",
        provider="openai",
        model_id="gpt-test",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        is_default=True,
        enabled=True,
        created_at="t",
        updated_at="t",
    )
    planner = Planner(model_store=store)
    planner.client = MagicMock()
    planner.client.complete.return_value = '["Step one", "Step two", "Step three"]'
    plan = planner.plan("ship feature X", agent_role="software_engineer")
    assert plan == ["Step one", "Step two", "Step three"]
    store.get_default.assert_called()
    planner.client.complete.assert_called_once()
    model_arg = planner.client.complete.call_args[0][0]
    assert model_arg.id == "m1"
    assert model_arg.model_id == "gpt-test"
