from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.config import REFERENCE_HTML, REFERENCE_SHA256
from app.db import queries
from app.db.connection import available_migrations, migrate, open_database, schema_version
from app.domain.models import normalize_tags
from app.importer import (
    ImportFormatError,
    LegacyRecord,
    extract_records,
    import_legacy_html,
    import_records,
    sha256_file,
)
from tests.conftest import SAMPLE_HTML


def _html(payload: str) -> str:
    return f'<html><script id="game-data" type="application/json">{payload}</script></html>'


def test_migrations_apply_once(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "m.sqlite3")
    latest = max(v for v, _ in available_migrations())
    assert schema_version(conn) == latest
    assert migrate(conn) == latest  # re-running is a no-op
    assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == latest
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_sample_import_round_trips_every_field(
    sample_db: sqlite3.Connection, sample_records: list[LegacyRecord]
) -> None:
    games = {g.appid: g for g in queries.load_legacy_games(sample_db)}
    assert len(games) == len(sample_records)
    for r in sample_records:
        g = games[r.appid]
        assert (g.name, g.short_description, g.release_year) == (
            r.name,
            r.short_description,
            r.release_year,
        )
        assert g.tags == normalize_tags(r.tags)
        assert g.price == r.price and g.review_score == r.review_score
        assert g.total_reviews == r.total_reviews
        assert g.estimated_revenue == r.estimated_revenue
        assert g.revenue_rank_in_year == r.revenue_rank_in_year
        assert g.qualifying_games_in_year == r.qualifying_games_in_year
        assert g.revenue_percentile_in_year == r.revenue_percentile_in_year


def test_raw_tags_and_provenance_preserved(
    sample_db: sqlite3.Connection, sample_records: list[LegacyRecord]
) -> None:
    padded = next(r for r in sample_records if any(t != t.strip() for t in r.tags))
    row = sample_db.execute(
        "SELECT tags_raw_json, price_display_context, is_free, data_source FROM games"
        " WHERE appid = ?",
        (padded.appid,),
    ).fetchone()
    assert json.loads(row["tags_raw_json"]) == padded.tags
    assert row["price_display_context"] == "legacy_price_context_unknown"
    assert row["is_free"] is None  # price 0 is never asserted as F2P
    m = sample_db.execute(
        "SELECT observed_at, source, estimate_model, data_quality_flags FROM game_metrics"
        " WHERE appid = ? AND is_legacy_snapshot = 1",
        (padded.appid,),
    ).fetchone()
    assert m["observed_at"] is None and m["source"] == "legacy_import"
    assert m["estimate_model"] == "legacy_reviews_x45_price"
    assert "tags_whitespace_trimmed" in json.loads(m["data_quality_flags"])


def test_import_is_idempotent_and_preserves_session_state(sample_db: sqlite3.Connection) -> None:
    appid = queries.load_legacy_games(sample_db)[0].appid
    queries.record_view(sample_db, "session-abc", appid, "suggested")
    before = {
        t: sample_db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("games", "game_metrics", "view_events", "view_sessions")
    }
    result = import_legacy_html(sample_db, SAMPLE_HTML)
    after = {t: sample_db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
    assert before == after
    assert result.inserted == 0 and result.updated == before["games"]
    assert queries.history_appids(sample_db, "session-abc") == [appid]
    assert sample_db.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 2


@pytest.mark.parametrize(
    ("html", "message"),
    [
        ("<html><body>no data</body></html>", "found 0"),
        (_html("{not json"), "not valid JSON"),
        (_html('{"a": 1}'), "JSON array"),
        (_html('[{"appid": 1}]'), "violates legacy contract"),
    ],
)
def test_malformed_sources_are_rejected(html: str, message: str) -> None:
    with pytest.raises(ImportFormatError, match=message):
        extract_records(html)


def test_wrong_types_and_extra_fields_are_rejected(sample_records: list[LegacyRecord]) -> None:
    good = sample_records[0].model_dump()
    for bad in ({**good, "appid": "1"}, {**good, "price": "3.99"}, {**good, "extra": 1}):
        with pytest.raises(ImportFormatError):
            extract_records(_html(json.dumps([bad])))
    with pytest.raises(ImportFormatError, match="duplicate appid"):
        extract_records(_html(json.dumps([good, good])))


def test_failed_import_rolls_back(tmp_path: Path, sample_records: list[LegacyRecord]) -> None:
    conn = open_database(tmp_path / "rb.sqlite3")
    # Force a failure on the second record; the first record's writes must be rolled back.
    conn.execute(
        "CREATE TRIGGER fail_second AFTER INSERT ON game_metrics"
        " WHEN NEW.legacy_source_index = 1 BEGIN SELECT RAISE(ABORT, 'boom'); END"
    )
    with pytest.raises(sqlite3.DatabaseError):
        import_records(conn, sample_records[:2], "x", "y")
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 0
    conn.close()


def test_missing_source_file(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "x.sqlite3")
    with pytest.raises(FileNotFoundError, match="never substitute"):
        import_legacy_html(conn, tmp_path / "missing.html")
    conn.close()


@pytest.mark.reference
def test_reference_file_unmodified() -> None:
    assert sha256_file(REFERENCE_HTML) == REFERENCE_SHA256
    assert REFERENCE_HTML.stat().st_size == 11_169_489


@pytest.mark.reference
def test_reference_import_matches_audit(reference_db_path: Path) -> None:
    conn = open_database(reference_db_path)
    games = queries.load_legacy_games(conn)
    info = queries.latest_import(conn)
    conn.close()
    assert info is not None and info.source_sha256 == REFERENCE_SHA256
    assert len(games) == 15_521 == len({g.appid for g in games})
    years: dict[int, int] = {}
    for g in games:
        years[g.release_year] = years.get(g.release_year, 0) + 1
    assert years == {2022: 3_946, 2023: 4_244, 2024: 4_982, 2025: 2_349}
    assert sum(g.estimated_revenue >= 100_000 for g in games) == 3_704
    assert sum(g.price == 0 for g in games) == 1_004
    assert len({t for g in games for t in g.tags}) == 443
    assert [g.source_index for g in games] == list(range(15_521))
    vs = next(g for g in games if g.appid == 1794680)
    assert (vs.name, vs.price, vs.total_reviews, vs.estimated_revenue) == (
        "Vampire Survivors",
        3.74,
        250_334,
        42_131_212,
    )
    assert (vs.revenue_rank_in_year, vs.qualifying_games_in_year) == (16, 3946)
    assert vs.revenue_percentile_in_year == 99.62
