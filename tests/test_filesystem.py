"""Filesystem tool jail + write/update tests."""

from __future__ import annotations

from pathlib import Path

from aeios.tools.filesystem import FilesystemTool


def test_filesystem_read_list(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    tool = FilesystemTool(root=tmp_path, allow_write=False)
    listed = tool.run(action="list", path=".")
    assert listed.ok is True
    assert "a.txt" in listed.output
    read = tool.run(action="read", path="a.txt")
    assert read.ok is True
    assert read.output == "hello"


def test_filesystem_write_in_jail(tmp_path: Path) -> None:
    tool = FilesystemTool(root=tmp_path, allow_write=True)
    result = tool.run(action="write", path="out/hello.py", content="print(1)\n")
    assert result.ok is True
    assert isinstance(result.output, dict)
    assert result.output["path"] == "out/hello.py"
    assert (tmp_path / "out" / "hello.py").read_text(encoding="utf-8") == "print(1)\n"


def test_filesystem_write_disabled(tmp_path: Path) -> None:
    tool = FilesystemTool(root=tmp_path, allow_write=False)
    result = tool.run(action="write", path="x.txt", content="nope")
    assert result.ok is False
    assert "disabled" in (result.error or "").lower()


def test_filesystem_update_append(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("base\n", encoding="utf-8")
    tool = FilesystemTool(root=tmp_path, allow_write=True)
    result = tool.run(action="update", path="notes.md", content="more\n", mode="append")
    assert result.ok is True
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "base\nmore\n"


def test_filesystem_update_missing_file(tmp_path: Path) -> None:
    tool = FilesystemTool(root=tmp_path, allow_write=True)
    result = tool.run(action="update", path="missing.txt", content="x")
    assert result.ok is False
    assert "Not a file" in (result.error or "")


def test_filesystem_rejects_jail_escape_write(tmp_path: Path) -> None:
    tool = FilesystemTool(root=tmp_path, allow_write=True)
    result = tool.run(action="write", path="../escape.txt", content="bad")
    assert result.ok is False
    assert "jail" in (result.error or "").lower()
    assert not (tmp_path.parent / "escape.txt").exists()


def test_filesystem_rejects_jail_escape_read(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    tool = FilesystemTool(root=tmp_path, allow_write=False)
    result = tool.run(action="read", path="../outside_secret.txt")
    assert result.ok is False
    assert "jail" in (result.error or "").lower()
