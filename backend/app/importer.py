"""Deterministic, offline, idempotent import of the legacy `steam_game_suggester.html` dataset.

* The embedded `<script id="game-data" type="application/json">` element is located with the
  stdlib HTML parser (no regex over rows) and decoded with `json`.
* Every record is validated against the 12-field legacy contract (strict types).
* Values are stored exactly as imported. Re-running the import upserts the same rows and never
  touches user-authored tables (sessions now; study status / notes in later phases).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr, ValidationError

from app.db.connection import utc_now
from app.domain.models import normalize_tags
from app.domain.revenue import (
    LEGACY_MODEL_ID,
    LEGACY_REVIEWS_TO_SALES_MULTIPLIER,
    legacy_estimate_usd,
    usd_to_minor_units,
)
from app.logging_config import get_logger

log = get_logger("importer")

LEGACY_SOURCE = "legacy_import"
LEGACY_PRICE_CONTEXT = "legacy_price_context_unknown"
LEGACY_FIELDS = (
    "appid",
    "name",
    "short_description",
    "tags",
    "release_year",
    "price",
    "total_reviews",
    "review_score",
    "estimated_revenue",
    "revenue_rank_in_year",
    "qualifying_games_in_year",
    "revenue_percentile_in_year",
)


class ImportFormatError(ValueError):
    """The source file is missing the dataset or the dataset violates the legacy contract."""


class LegacyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    appid: StrictInt
    name: StrictStr
    short_description: StrictStr
    tags: list[StrictStr]
    release_year: StrictInt
    price: StrictFloat | StrictInt
    total_reviews: StrictInt
    review_score: StrictFloat | StrictInt
    estimated_revenue: StrictInt
    revenue_rank_in_year: StrictInt
    qualifying_games_in_year: StrictInt
    revenue_percentile_in_year: StrictFloat | StrictInt


class _GameDataExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._capturing = False
        self._chunks: list[str] = []
        self.found = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("id") == "game-data":
            self._capturing = True
            self.found += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._capturing = False

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._chunks.append(data)

    @property
    def payload(self) -> str:
        return "".join(self._chunks)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_records(html_text: str) -> list[LegacyRecord]:
    extractor = _GameDataExtractor()
    extractor.feed(html_text)
    extractor.close()
    if extractor.found != 1:
        raise ImportFormatError(f"expected exactly one script#game-data, found {extractor.found}")
    try:
        raw = json.loads(extractor.payload)
    except json.JSONDecodeError as exc:
        raise ImportFormatError(f"game-data is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise ImportFormatError("game-data must be a JSON array")
    records: list[LegacyRecord] = []
    items: list[object] = raw  # pyright: ignore[reportUnknownVariableType]
    for index, item in enumerate(items):
        try:
            records.append(LegacyRecord.model_validate(item))
        except ValidationError as exc:
            raise ImportFormatError(f"record {index} violates legacy contract: {exc}") from exc
    seen: set[int] = set()
    for record in records:
        if record.appid in seen:
            raise ImportFormatError(f"duplicate appid {record.appid}")
        seen.add(record.appid)
    return records


@dataclass(frozen=True, slots=True)
class ImportResult:
    source_sha256: str
    record_count: int
    inserted: int
    updated: int
    quality_flagged: int


def _quality_flags(record: LegacyRecord) -> list[str]:
    flags: list[str] = []
    if legacy_estimate_usd(record.total_reviews, float(record.price)) != record.estimated_revenue:
        flags.append("legacy_revenue_formula_mismatch")
    if record.price == 0:
        flags.append("price_zero_f2p_unverified")
    if not record.short_description:
        flags.append("empty_description")
    if any(tag != tag.strip() for tag in record.tags):
        flags.append("tags_whitespace_trimmed")
    return flags


def import_records(
    conn: sqlite3.Connection,
    records: list[LegacyRecord],
    source_path: str,
    source_sha256: str,
) -> ImportResult:
    now = utc_now()
    inserted = updated = flagged = 0
    params = json.dumps({"reviews_to_sales_multiplier": LEGACY_REVIEWS_TO_SALES_MULTIPLIER})
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = {row[0] for row in conn.execute("SELECT appid FROM games")}
        for index, r in enumerate(records):
            tags = list(normalize_tags(r.tags))
            price_minor = usd_to_minor_units(float(r.price))
            conn.execute(
                """
                INSERT INTO games (appid, name, short_description, release_year,
                    price_minor_units, currency_code, price_display_context, is_free,
                    tags_json, tags_raw_json, tags_source, data_source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'USD', ?, NULL, ?, ?, 'legacy_html', ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                    name = excluded.name,
                    short_description = excluded.short_description,
                    release_year = excluded.release_year,
                    price_minor_units = excluded.price_minor_units,
                    currency_code = excluded.currency_code,
                    price_display_context = excluded.price_display_context,
                    tags_json = excluded.tags_json,
                    tags_raw_json = excluded.tags_raw_json,
                    tags_source = excluded.tags_source,
                    updated_at = excluded.updated_at
                WHERE games.data_source = 'legacy_html'
                """,
                (
                    r.appid,
                    r.name,
                    r.short_description,
                    r.release_year,
                    price_minor,
                    LEGACY_PRICE_CONTEXT,
                    json.dumps(tags, ensure_ascii=False),
                    json.dumps(r.tags, ensure_ascii=False),
                    LEGACY_SOURCE,
                    now,
                    now,
                ),
            )
            flags = _quality_flags(r)
            flagged += bool(flags)
            conn.execute(
                """
                INSERT INTO game_metrics (appid, observed_at, imported_at, source, total_reviews,
                    review_score, price_minor_units, currency_code, price_type, legacy_price,
                    estimated_revenue_minor_units, legacy_estimated_revenue, estimate_model,
                    estimate_params_json, legacy_rank_in_year, legacy_qualifying_games_in_year,
                    legacy_revenue_percentile_in_year, legacy_source_index, is_legacy_snapshot,
                    data_quality_flags)
                VALUES (?, NULL, ?, ?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(appid) WHERE is_legacy_snapshot = 1 DO UPDATE SET
                    imported_at = excluded.imported_at,
                    total_reviews = excluded.total_reviews,
                    review_score = excluded.review_score,
                    price_minor_units = excluded.price_minor_units,
                    legacy_price = excluded.legacy_price,
                    estimated_revenue_minor_units = excluded.estimated_revenue_minor_units,
                    legacy_estimated_revenue = excluded.legacy_estimated_revenue,
                    legacy_rank_in_year = excluded.legacy_rank_in_year,
                    legacy_qualifying_games_in_year = excluded.legacy_qualifying_games_in_year,
                    legacy_revenue_percentile_in_year = excluded.legacy_revenue_percentile_in_year,
                    legacy_source_index = excluded.legacy_source_index,
                    data_quality_flags = excluded.data_quality_flags
                """,
                (
                    r.appid,
                    now,
                    LEGACY_SOURCE,
                    r.total_reviews,
                    float(r.review_score),
                    price_minor,
                    LEGACY_PRICE_CONTEXT,
                    float(r.price),
                    r.estimated_revenue * 100,
                    r.estimated_revenue,
                    LEGACY_MODEL_ID,
                    params,
                    r.revenue_rank_in_year,
                    r.qualifying_games_in_year,
                    float(r.revenue_percentile_in_year),
                    index,
                    json.dumps(flags),
                ),
            )
            if r.appid in existing:
                updated += 1
            else:
                inserted += 1
        conn.execute(
            "INSERT INTO import_runs (source_path, source_sha256, record_count, inserted, updated,"
            " imported_at) VALUES (?, ?, ?, ?, ?, ?)",
            (source_path, source_sha256, len(records), inserted, updated, now),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    result = ImportResult(source_sha256, len(records), inserted, updated, flagged)
    log.info("legacy import complete", extra={"result": repr(result)})
    return result


def import_legacy_html(conn: sqlite3.Connection, source: Path) -> ImportResult:
    if not source.is_file():
        raise FileNotFoundError(
            f"{source} not found. Place the original steam_game_suggester.html there; "
            "never substitute invented data."
        )
    digest = sha256_file(source)
    records = extract_records(source.read_text(encoding="utf-8"))
    return import_records(conn, records, source.name, digest)
