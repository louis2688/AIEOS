from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from aeios.core.types import ToolResult
from aeios.tools.base import BaseTool

# Cross-platform safe binaries (read-oriented / already used by the kernel).
# Windows note: cmd builtins like ``dir`` / ``type`` are NOT allowlisted — they
# require ``cmd /c`` which breaks the argv jail. Prefer ``ls``/``cat`` via Git
# Bash/WSL, or ``py`` / ``python`` for listing and reading files.
DEFAULT_ALLOWLIST = frozenset(
    {
        "ls",
        "pwd",
        "echo",
        "cat",
        "head",
        "tail",
        "wc",
        "rg",
        "grep",
        "find",
        "python",
        "python3",
        "py",  # Windows Python launcher
        "pytest",
        "git",
        "uname",
        "whoami",
        "date",
        "where",  # Windows: locate binaries (no write)
        "which",
    }
)

# git subcommands that are read-only by default (no write-git)
SAFE_GIT = frozenset({"status", "log", "diff", "show", "branch", "rev-parse", "remote"})

# git flags that take a path and can escape the workspace jail
_GIT_PATH_FLAGS = frozenset(
    {
        "-C",
        "--git-dir",
        "--work-tree",
    }
)

_WIN_SUFFIXES = (".exe", ".cmd", ".bat", ".com")


def normalize_binary(name: str) -> str:
    """Strip Windows executable suffixes for allowlist matching."""
    base = Path(name).name
    if sys.platform == "win32":
        lower = base.lower()
        for ext in _WIN_SUFFIXES:
            if lower.endswith(ext):
                return base[: -len(ext)]
    return base


def _is_path_like(arg: str) -> bool:
    if not arg or arg.startswith("-"):
        return False
    if os.path.isabs(arg):
        return True
    if arg in {".", ".."} or arg.startswith(".."):
        return True
    return "/" in arg or "\\" in arg


class ShellTool(BaseTool):
    name = "shell"
    description = "Run an allowlisted command inside the workspace jail."

    def __init__(
        self,
        root: Path,
        allowlist: set[str] | frozenset[str] | None = None,
        timeout_sec: float = 15.0,
    ) -> None:
        self.root = root.resolve()
        self.allowlist = frozenset(allowlist or DEFAULT_ALLOWLIST)
        self.timeout_sec = timeout_sec

    def run(self, command: str = "", **_: Any) -> ToolResult:
        if not command or not command.strip():
            return ToolResult(ok=False, error="Empty command")

        try:
            # Always posix parsing so quoted -c scripts strip quotes the same on
            # Windows. Path jail still accepts ``\`` in path-like arguments.
            argv = shlex.split(command)
        except ValueError as exc:
            return ToolResult(ok=False, error=f"Invalid command: {exc}")

        if not argv:
            return ToolResult(ok=False, error="Empty command")

        binary = normalize_binary(argv[0])
        if binary not in self.allowlist:
            return ToolResult(
                ok=False,
                error=f"Command not allowlisted: {binary}. Allowed: {sorted(self.allowlist)}",
            )

        if binary == "git":
            denied = self._check_git(argv)
            if denied is not None:
                return denied

        escaped = self._find_jail_escape(argv)
        if escaped is not None:
            return ToolResult(ok=False, error=f"Path escapes workspace jail: {escaped}")

        try:
            completed = subprocess.run(
                argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error=f"Timed out after {self.timeout_sec}s")
        except OSError as exc:
            return ToolResult(ok=False, error=str(exc))

        output = {
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-4000:],
        }
        if completed.returncode != 0:
            return ToolResult(ok=False, output=output, error=f"Exit code {completed.returncode}")
        return ToolResult(ok=True, output=output)

    def _check_git(self, argv: list[str]) -> ToolResult | None:
        # Find the first non-flag token as the subcommand (skip -C <path> pairs etc.)
        i = 1
        while i < len(argv):
            arg = argv[i]
            if arg in _GIT_PATH_FLAGS:
                return ToolResult(
                    ok=False,
                    error=f"git flag not allowed (jail): {arg}",
                )
            if arg.startswith("-"):
                # Long options with =value, or short flags without path args
                if arg.startswith("--git-dir=") or arg.startswith("--work-tree="):
                    return ToolResult(
                        ok=False,
                        error=f"git flag not allowed (jail): {arg.split('=', 1)[0]}",
                    )
                i += 1
                continue
            sub = arg
            if sub not in SAFE_GIT:
                return ToolResult(
                    ok=False,
                    error=f"git subcommand not allowed: {sub or '(none)'}. Allowed: {sorted(SAFE_GIT)}",
                )
            return None
        return ToolResult(
            ok=False,
            error=f"git subcommand not allowed: (none). Allowed: {sorted(SAFE_GIT)}",
        )

    def _find_jail_escape(self, argv: list[str]) -> str | None:
        for arg in argv[1:]:
            if not _is_path_like(arg):
                continue
            if self._escapes_root(arg):
                return arg
        return None

    def _escapes_root(self, arg: str) -> bool:
        try:
            if Path(arg).is_absolute():
                candidate = Path(arg).resolve()
            else:
                candidate = (self.root / arg).resolve()
            candidate.relative_to(self.root)
            return False
        except (ValueError, OSError):
            return True
