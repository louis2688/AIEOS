from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from aeios.core.types import ToolResult
from aeios.tools.base import BaseTool

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
        "pytest",
        "git",
        "uname",
        "whoami",
        "date",
    }
)

# git subcommands that are read-only by default
SAFE_GIT = frozenset({"status", "log", "diff", "show", "branch", "rev-parse", "remote"})


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
            argv = shlex.split(command)
        except ValueError as exc:
            return ToolResult(ok=False, error=f"Invalid command: {exc}")

        if not argv:
            return ToolResult(ok=False, error="Empty command")

        binary = Path(argv[0]).name
        if binary not in self.allowlist:
            return ToolResult(
                ok=False,
                error=f"Command not allowlisted: {binary}. Allowed: {sorted(self.allowlist)}",
            )

        if binary == "git":
            sub = argv[1] if len(argv) > 1 else ""
            if sub not in SAFE_GIT:
                return ToolResult(
                    ok=False,
                    error=f"git subcommand not allowed: {sub or '(none)'}. Allowed: {sorted(SAFE_GIT)}",
                )

        # Reject path escapes via arguments that resolve outside root.
        for arg in argv[1:]:
            if arg.startswith("-"):
                continue
            if "/" in arg or arg.startswith(".."):
                candidate = (self.root / arg).resolve() if not Path(arg).is_absolute() else Path(arg).resolve()
                if not str(candidate).startswith(str(self.root)):
                    return ToolResult(ok=False, error=f"Path escapes workspace jail: {arg}")

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
