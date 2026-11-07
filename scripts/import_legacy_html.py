"""Import the legacy HTML dataset into SQLite (offline, idempotent).

Usage:
    uv run python scripts/import_legacy_html.py \
        [--source reference/steam_game_suggester.html] [--db .local/data/catalog.sqlite3]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import REFERENCE_HTML, REFERENCE_SHA256, load_settings
from app.db.connection import open_database
from app.importer import ImportFormatError, import_legacy_html, sha256_file

MISSING = (
    "reference/steam_game_suggester.html is missing. It is part of the repository: "
    "restore it with 'git checkout -- reference'."
)


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--source", type=Path, default=REFERENCE_HTML)
    parser.add_argument("--db", type=Path, default=settings.catalog_path)
    parser.add_argument(
        "--allow-other-source",
        action="store_true",
        help="Permit a source whose SHA-256 differs from the verified reference (fixtures).",
    )
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"ERROR: source not found: {args.source}", file=sys.stderr)
        if args.source == REFERENCE_HTML:
            print(f"       {MISSING}", file=sys.stderr)
        return 2
    digest = sha256_file(args.source)
    if digest != REFERENCE_SHA256 and not args.allow_other_source:
        print(
            f"ERROR: {args.source} SHA-256 {digest} != verified reference {REFERENCE_SHA256}."
            " Pass --allow-other-source for fixtures.",
            file=sys.stderr,
        )
        return 3
    conn = open_database(args.db)
    try:
        result = import_legacy_html(conn, args.source)
    except ImportFormatError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    finally:
        conn.close()
    print(
        f"Imported {result.record_count} records into {args.db}"
        f" (inserted {result.inserted}, updated {result.updated},"
        f" quality-flagged {result.quality_flagged}); sha256={result.source_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
