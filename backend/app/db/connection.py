"""SQLite connection helpers and the numbered-migration runner."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.logging_config import get_logger

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
log = get_logger("db")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: autocommit; multi-statement writes use explicit BEGIN/COMMIT.
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def available_migrations() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        found.append((version, path))
    return found


def schema_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations, each in its own transaction. Returns the final version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    current = schema_version(conn)
    for version, path in available_migrations():
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(
                f"BEGIN;\n{sql}\n;"
                f"INSERT INTO schema_migrations(version, applied_at) "
                f"VALUES ({version}, '{utc_now()}');\nCOMMIT;"
            )
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        log.info("migration applied", extra={"version": version, "file": path.name})
        current = version
    return current


def open_database(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    return conn
