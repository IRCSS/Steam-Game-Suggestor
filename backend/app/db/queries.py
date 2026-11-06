"""Repository functions. SQL lives here; domain modules stay pure."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from app.domain.models import Game


@dataclass(frozen=True, slots=True)
class ImportInfo:
    source_sha256: str
    record_count: int
    imported_at: str
    run_id: int


def latest_import(conn: sqlite3.Connection) -> ImportInfo | None:
    row = conn.execute(
        "SELECT id, source_sha256, record_count, imported_at FROM import_runs"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return ImportInfo(row["source_sha256"], row["record_count"], row["imported_at"], row["id"])


def load_legacy_games(conn: sqlite3.Connection) -> list[Game]:
    """All games with a legacy snapshot, in original source order."""
    rows = conn.execute(
        """
        SELECT g.appid, g.name, g.short_description, g.tags_json, g.release_year,
               m.legacy_price, m.total_reviews, m.review_score, m.legacy_estimated_revenue,
               m.legacy_rank_in_year, m.legacy_qualifying_games_in_year,
               m.legacy_revenue_percentile_in_year, m.legacy_source_index
        FROM games g
        JOIN game_metrics m ON m.appid = g.appid AND m.is_legacy_snapshot = 1
        ORDER BY m.legacy_source_index
        """
    ).fetchall()
    return [
        Game(
            appid=row["appid"],
            name=row["name"],
            short_description=row["short_description"] or "",
            tags=tuple(json.loads(row["tags_json"])),
            release_year=row["release_year"],
            price=row["legacy_price"],
            total_reviews=row["total_reviews"],
            review_score=row["review_score"],
            estimated_revenue=row["legacy_estimated_revenue"],
            revenue_rank_in_year=row["legacy_rank_in_year"],
            qualifying_games_in_year=row["legacy_qualifying_games_in_year"],
            revenue_percentile_in_year=row["legacy_revenue_percentile_in_year"],
            source_index=row["legacy_source_index"],
            legacy_rank_in_year=row["legacy_rank_in_year"],
            legacy_qualifying_games_in_year=row["legacy_qualifying_games_in_year"],
            legacy_revenue_percentile_in_year=row["legacy_revenue_percentile_in_year"],
        )
        for row in rows
    ]
