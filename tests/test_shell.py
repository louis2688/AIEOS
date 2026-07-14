from pathlib import Path

from aeios.tools.shell import ShellTool


def test_shell_allowlist_and_pwd(tmp_path: Path) -> None:
    tool = ShellTool(root=tmp_path)
    ok = tool.run(command="pwd")
    assert ok.ok is True
    assert str(tmp_path) in str(ok.output["stdout"]).rstrip() or ok.output["stdout"]


def test_shell_rejects_unknown_binary(tmp_path: Path) -> None:
    tool = ShellTool(root=tmp_path)
    bad = tool.run(command="rm -rf /")
    assert bad.ok is False
    assert "not allowlisted" in (bad.error or "")


def test_shell_rejects_unsafe_git(tmp_path: Path) -> None:
    tool = ShellTool(root=tmp_path)
    bad = tool.run(command="git push")
    assert bad.ok is False
    assert "not allowed" in (bad.error or "")
