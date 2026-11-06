"""Online backup of the local SQLite database (safe while the API is running).

Usage: uv run python scripts/backup_db.py [--db PATH] [--out-dir .local/backups]
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.config import REPO_ROOT, load_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=load_settings().db_path)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / ".local" / "backups")
    args = parser.parse_args()
    if not args.db.is_file():
        raise SystemExit(f"database not found: {args.db}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = args.out_dir / f"{args.db.stem}-{stamp}.sqlite3"
    with sqlite3.connect(args.db) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    print(f"backup written to {target}")


if __name__ == "__main__":
    main()
