"""Thin SQL adapter for SQLite (default) and Postgres.

Stores keep using ``?`` placeholders; Postgres translates them to ``%s``.
Schema is create-if-not-exists (MVP — no migration framework).
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Literal, Sequence

Backend = Literal["sqlite", "postgres"]


def is_postgres_url(database_url: str) -> bool:
    u = (database_url or "").strip().lower()
    return u.startswith("postgres://") or u.startswith("postgresql://") or u.startswith(
        "postgresql+"
    )


def is_sqlite_url(database_url: str) -> bool:
    return (database_url or "").strip().lower().startswith("sqlite:")


def normalize_postgres_url(database_url: str) -> str:
    """Strip SQLAlchemy-style driver suffixes for psycopg."""
    url = database_url.strip()
    # postgresql+psycopg://… → postgresql://…
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url, count=1, flags=re.I)


def resolve_sqlite_path(database_url: str, data_dir: Path, workspace: Path) -> Path:
    if database_url.startswith("sqlite:///"):
        raw = database_url.removeprefix("sqlite:///")
        path = Path(raw)
        if not path.is_absolute():
            path = workspace / path
        return path
    return data_dir / "aeios.db"


class SqlRow:
    """Dict-like row shared by sqlite and postgres backends."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def __iter__(self):
        return iter(self._data)

    def __repr__(self) -> str:
        return f"SqlRow({self._data!r})"


class SqlResult:
    __slots__ = ("rowcount", "_rows")

    def __init__(self, rows: list[SqlRow], rowcount: int) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> SqlRow | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[SqlRow]:
        return list(self._rows)


class SqlDb:
    """Minimal connection wrapper used by AEIOS stores."""

    def __init__(self, backend: Backend, *, display: str) -> None:
        self.backend = backend
        self.display = display
        self._lock = threading.Lock()

    @property
    def path(self) -> Path | None:
        """Filesystem path for sqlite; None for postgres."""
        return None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> SqlResult:
        raise NotImplementedError

    def executescript(self, script: str) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def healthy(self) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def lock(self) -> threading.Lock:
        return self._lock

    def adapt_sql(self, sql: str) -> str:
        if self.backend == "postgres":
            return sql.replace("?", "%s")
        return sql

    def serial_pk(self, column: str = "id") -> str:
        if self.backend == "postgres":
            return f"{column} BIGSERIAL PRIMARY KEY"
        return f"{column} INTEGER PRIMARY KEY AUTOINCREMENT"

    def now_default(self) -> str:
        if self.backend == "postgres":
            return "DEFAULT (NOW() AT TIME ZONE 'utc')"
        return "DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


class SqliteDb(SqlDb):
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__("sqlite", display=str(db_path))
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    @property
    def path(self) -> Path | None:
        return self._path

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> SqlResult:
        cur = self._conn.execute(sql, tuple(params or ()))
        rows = [SqlRow(dict(r)) for r in cur.fetchall()]
        return SqlResult(rows, cur.rowcount)

    def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    def commit(self) -> None:
        self._conn.commit()

    def healthy(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class PostgresDb(SqlDb):
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Postgres support requires psycopg. Install with: pip install 'aeios[postgres]'"
            ) from exc

        url = normalize_postgres_url(database_url)
        # Redact password for display
        display = re.sub(r":([^:@/]+)@", ":***@", url)
        super().__init__("postgres", display=display)
        self._conn = psycopg.connect(url, row_factory=dict_row)
        self._conn.autocommit = False

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> SqlResult:
        adapted = self.adapt_sql(sql)
        with self._conn.cursor() as cur:
            cur.execute(adapted, tuple(params or ()))
            rows: list[SqlRow] = []
            if cur.description:
                raw = cur.fetchall()
                rows = [SqlRow(dict(r)) for r in raw]
            return SqlResult(rows, cur.rowcount if cur.rowcount is not None else 0)

    def executescript(self, script: str) -> None:
        # Split on semicolons; skip empty chunks. Good enough for MVP DDL.
        parts = [p.strip() for p in script.split(";") if p.strip()]
        with self._conn.cursor() as cur:
            for part in parts:
                cur.execute(part)

    def commit(self) -> None:
        self._conn.commit()

    def healthy(self) -> bool:
        try:
            with self._lock:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return True
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def open_db(
    database_url: str,
    *,
    workspace: Path,
    data_dir: Path,
) -> SqlDb:
    """Open sqlite (default) or postgres from DATABASE_URL."""
    if is_postgres_url(database_url):
        return PostgresDb(database_url)
    path = resolve_sqlite_path(database_url, data_dir, workspace)
    return SqliteDb(path)


def coerce_db(db: SqlDb | Path) -> SqlDb:
    """Accept an existing SqlDb or a Path (opens sqlite)."""
    if isinstance(db, SqlDb):
        return db
    return SqliteDb(Path(db))
