from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point DB at the per-test temp dir so kernels don't share state."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'data' / 'aeios.db'}")
    monkeypatch.setenv("AEIOS_ENV", "test")
