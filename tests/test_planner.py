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
