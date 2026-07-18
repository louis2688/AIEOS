import sys
from pathlib import Path

from aeios.tools.shell import ShellTool, normalize_binary


def test_shell_allowlist_and_cwd(tmp_path: Path) -> None:
    tool = ShellTool(root=tmp_path)
    # Cross-platform: pwd is often missing on Windows; python is allowlisted.
    ok = tool.run(command='python -c "import os; print(os.getcwd())"')
    assert ok.ok is True
    assert str(tmp_path.resolve()) in str(ok.output["stdout"]).replace("\\\\", "\\")


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


def test_shell_rejects_git_path_flags(tmp_path: Path) -> None:
    tool = ShellTool(root=tmp_path)
    bad = tool.run(command="git -C /tmp status")
    assert bad.ok is False
    assert "jail" in (bad.error or "").lower() or "not allowed" in (bad.error or "")


def test_shell_rejects_path_escape(tmp_path: Path) -> None:
    tool = ShellTool(root=tmp_path)
    bad = tool.run(command="cat ../outside.txt")
    assert bad.ok is False
    assert "jail" in (bad.error or "").lower()


def test_normalize_binary_strips_windows_suffix() -> None:
    if sys.platform == "win32":
        assert normalize_binary("python.exe") == "python"
        assert normalize_binary(r"C:\Python\python.EXE") == "python"
    else:
        assert normalize_binary("python3") == "python3"


def test_py_is_allowlisted(tmp_path: Path) -> None:
    tool = ShellTool(root=tmp_path)
    # May fail if py is missing; only assert allowlist acceptance vs unknown binary
    result = tool.run(command='py -c "print(1)"')
    if result.ok:
        assert "1" in str(result.output.get("stdout", ""))
    else:
        assert "not allowlisted" not in (result.error or "")
