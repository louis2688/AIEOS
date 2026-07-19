"""Agent package — lazy exports to avoid import cycles with the kernel."""

from __future__ import annotations

from typing import Any

__all__ = ["ArchitectAgent", "EchoAgent", "SoftwareEngineerAgent"]


def __getattr__(name: str) -> Any:
    if name == "ArchitectAgent":
        from aeios.agents.architect import ArchitectAgent

        return ArchitectAgent
    if name == "EchoAgent":
        from aeios.agents.echo import EchoAgent

        return EchoAgent
    if name == "SoftwareEngineerAgent":
        from aeios.agents.software_engineer import SoftwareEngineerAgent

        return SoftwareEngineerAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
