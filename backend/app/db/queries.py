"""Repository functions. SQL lives here; domain modules stay pure."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from app.db.connection import utc_now
from app.domain.models import LegacyGame

HISTORY_LIMIT = 12


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


def load_legacy_games(conn: sqlite3.Connection) -> list[LegacyGame]:
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
        LegacyGame(
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
        )
        for row in rows
    ]


# --- Session view events -------------------------------------------------------------------


def ensure_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO view_sessions(session_id, created_at) VALUES (?, ?)",
        (session_id, utc_now()),
    )


def _markers(conn: sqlite3.Connection, session_id: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT repeat_reset_after_event_id, history_cleared_after_event_id"
        " FROM view_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return (0, 0)
    return (int(row[0]), int(row[1]))


def seen_appids(conn: sqlite3.Connection, session_id: str) -> frozenset[int]:
    """AppIDs shown this session since the last repeat reset / history clear."""
    repeat_marker, history_marker = _markers(conn, session_id)
    marker = max(repeat_marker, history_marker)
    rows = conn.execute(
        "SELECT DISTINCT appid FROM view_events WHERE session_id = ? AND id > ?",
        (session_id, marker),
    )
    return frozenset(int(r[0]) for r in rows)


def record_view(conn: sqlite3.Connection, session_id: str, appid: int, source: str) -> int:
    ensure_session(conn, session_id)
    cursor = conn.execute(
        "INSERT INTO view_events(session_id, appid, shown_at, source) VALUES (?, ?, ?, ?)",
        (session_id, appid, utc_now(), source),
    )
    return int(cursor.lastrowid or 0)


def _max_event_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM view_events").fetchone()
    return int(row[0])


def reset_repeat_history(conn: sqlite3.Connection, session_id: str) -> None:
    """Forget 'seen' AppIDs for repeat avoidance; the visible history list is kept (legacy)."""
    ensure_session(conn, session_id)
    conn.execute(
        "UPDATE view_sessions SET repeat_reset_after_event_id = ? WHERE session_id = ?",
        (_max_event_id(conn), session_id),
    )


def clear_history(conn: sqlite3.Connection, session_id: str) -> None:
    """Legacy 'Clear': empties both the history list and the seen set."""
    ensure_session(conn, session_id)
    conn.execute(
        "UPDATE view_sessions SET history_cleared_after_event_id = ? WHERE session_id = ?",
        (_max_event_id(conn), session_id),
    )


def history_appids(
    conn: sqlite3.Connection, session_id: str, limit: int = HISTORY_LIMIT
) -> list[int]:
    """Most recent distinct AppIDs shown this session (newest first)."""
    _, history_marker = _markers(conn, session_id)
    rows = conn.execute(
        """
        SELECT appid, MAX(id) AS last_id FROM view_events
        WHERE session_id = ? AND id > ?
        GROUP BY appid ORDER BY last_id DESC LIMIT ?
        """,
        (session_id, history_marker, limit),
    )
    return [int(r[0]) for r in rows]
