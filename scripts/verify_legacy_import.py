"""Verify an imported database against the audited legacy figures and the source file.

Checks record counts, year distribution, $100K count, price-zero count, and a field-by-field
round trip of every record against the original embedded JSON.

Usage: uv run python scripts/verify_legacy_import.py [--db PATH] [--source PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import REFERENCE_HTML, REFERENCE_SHA256, load_settings
from app.db.connection import open_database
from app.db.queries import latest_import, load_legacy_games
from app.domain.models import normalize_tags
from app.importer import extract_records, sha256_file

EXPECTED = {
    "records": 15_521,
    "years": {2022: 3_946, 2023: 4_244, 2024: 4_982, 2025: 2_349},
    "revenue_ge_100k": 3_704,
    "price_zero": 1_004,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=load_settings().catalog_path)
    parser.add_argument("--source", type=Path, default=REFERENCE_HTML)
    args = parser.parse_args(argv)

    failures: list[str] = []

    def check(label: str, actual: object, expected: object) -> None:
        ok = actual == expected
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {actual}" + ("" if ok else f" != {expected}"))
        if not ok:
            failures.append(label)

    check("source sha256", sha256_file(args.source), REFERENCE_SHA256)
    conn = open_database(args.db)
    games = load_legacy_games(conn)
    info = latest_import(conn)
    conn.close()
    check("import run sha256", info.source_sha256 if info else None, REFERENCE_SHA256)
    check("records", len(games), EXPECTED["records"])
    check("unique appids", len({g.appid for g in games}), EXPECTED["records"])
    years: dict[int, int] = {}
    for g in games:
        years[g.release_year] = years.get(g.release_year, 0) + 1
    check("year counts", dict(sorted(years.items())), EXPECTED["years"])
    check(
        ">= $100K", sum(g.estimated_revenue >= 100_000 for g in games), EXPECTED["revenue_ge_100k"]
    )
    check("price == 0", sum(g.price == 0 for g in games), EXPECTED["price_zero"])

    source = {r.appid: r for r in extract_records(args.source.read_text(encoding="utf-8"))}
    mismatched = 0
    for g in games:
        r = source[g.appid]
        same = (
            g.name == r.name
            and g.short_description == r.short_description
            and g.tags == normalize_tags(r.tags)
            and g.release_year == r.release_year
            and g.price == r.price
            and g.total_reviews == r.total_reviews
            and g.review_score == r.review_score
            and g.estimated_revenue == r.estimated_revenue
            and g.revenue_rank_in_year == r.revenue_rank_in_year
            and g.qualifying_games_in_year == r.qualifying_games_in_year
            and g.revenue_percentile_in_year == r.revenue_percentile_in_year
        )
        mismatched += not same
    check("field-by-field mismatches", mismatched, 0)

    print("OK" if not failures else f"FAILED: {', '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
