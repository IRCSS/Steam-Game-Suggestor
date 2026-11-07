"""Dataset export: the local data as plain tables, for analysis in any language or tool.

Every table is written twice, as CSV and as JSON (a list of objects with the same keys). In CSV,
list values (tags, review points) are JSON arrays inside the cell, so they parse unambiguously;
empty cells are unknown values. Pure module - no I/O.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.models import Game
from app.domain.observations import ReviewsObservation
from app.domain.research import Economics, Estimate, ResearchFindings

DATASET_FORMAT_VERSION = "1"

Row = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Table:
    name: str  # file stem: <name>.csv / <name>.json
    description: str
    columns: tuple[tuple[str, str], ...]  # (column, meaning)
    rows: list[Row]

    def csv_cell(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list | tuple | dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


GAME_COLUMNS: tuple[tuple[str, str], ...] = (
    ("appid", "Steam AppID (unique key; joins all tables)"),
    ("name", "game name"),
    ("release_year", "release year"),
    ("release_date", "release date (YYYY-MM-DD) when known from Steam, else empty"),
    ("price_usd", "listed price in USD (not a historical or sale price)"),
    ("is_free", "free to play; empty = unknown"),
    ("total_reviews", "Steam reviews, all languages"),
    ("review_score", "percent positive reviews"),
    ("estimated_revenue_usd", "ESTIMATE: total_reviews x 45 x price_usd (gross, not actual)"),
    ("revenue_rank_in_year", "rank by estimated revenue among qualifying games of the same year"),
    ("qualifying_games_in_year", "number of qualifying games in that year"),
    ("revenue_percentile_in_year", "percentile of the estimated revenue within the year"),
    ("qualifies", "estimated revenue meets the app's qualification floor"),
    ("english", "supports English; empty = not checked"),
    ("in_studies", "added to Studies"),
    ("tags", "Steam user tags (JSON array)"),
    ("short_description", "Steam short description"),
    ("data_source", "legacy_import | steam (refreshed from Steam) | steam_new (found later)"),
    ("reviews_observed_at", "when the review numbers were fetched; empty = legacy snapshot"),
    ("store_observed_at", "when price/date/description were fetched; empty = legacy snapshot"),
)

STUDY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("appid", "Steam AppID"),
    ("name", "game name"),
    ("status", "study status"),
    ("added_at", "when it was added (UTC, ISO 8601)"),
    ("added_by", "PC that added it"),
    ("updated_at", "last change (UTC, ISO 8601)"),
    ("notes", "user notes"),
)


def _estimate_columns(prefix: str, unit: str) -> tuple[tuple[str, str], ...]:
    return (
        (f"{prefix}_low", f"ESTIMATE, low end ({unit})"),
        (f"{prefix}_best", f"ESTIMATE, best guess ({unit})"),
        (f"{prefix}_high", f"ESTIMATE, high end ({unit})"),
        (f"{prefix}_confidence", "high | medium | low | unknown"),
    )


RESEARCH_COLUMNS: tuple[tuple[str, str], ...] = (
    ("appid", "Steam AppID"),
    ("name", "game name"),
    ("studio", "developer, per LLM web research"),
    *_estimate_columns("team_size", "people who worked on the game"),
    *_estimate_columns("development_months", "months from start to 1.0 release"),
    ("person_years_best", "team_size_best x development_months_best / 12"),
    ("cost_best", "ESTIMATE: person-years x salary per person-year (cost_currency)"),
    ("cost_currency", "currency of cost_best (from the app's cost model)"),
    ("cost_usd_best", "cost_best converted to USD"),
    ("break_even_gross_usd_best", "gross revenue at which the share after the platform cut = cost"),
    ("revenue_multiple", "estimated_revenue_usd / break_even_gross_usd_best"),
    ("budget_researched_at", "when team size / development time were researched"),
    ("why_it_worked", "review analysis: reasons it did well (JSON array of headlines)"),
    ("what_held_it_back", "review analysis: reasons it did not do better (JSON array)"),
    ("reviews_researched_at", "when the reviews were analyzed"),
)

REVIEW_HISTORY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("appid", "Steam AppID"),
    ("fetched_at", "when Steam was asked (UTC, ISO 8601)"),
    ("total_reviews", "reviews, all languages"),
    ("total_positive", "positive reviews"),
    ("total_negative", "negative reviews"),
)


def game_rows(
    games: Iterable[Game],
    qualifying: frozenset[int],
    english: Mapping[int, bool],
    studies: frozenset[int],
) -> list[Row]:
    return [
        {
            "appid": g.appid,
            "name": g.name,
            "release_year": g.release_year,
            "release_date": g.release_date,
            "price_usd": g.price,
            "is_free": g.is_free,
            "total_reviews": g.total_reviews,
            "review_score": g.review_score,
            "estimated_revenue_usd": g.estimated_revenue,
            "revenue_rank_in_year": g.revenue_rank_in_year,
            "qualifying_games_in_year": g.qualifying_games_in_year,
            "revenue_percentile_in_year": g.revenue_percentile_in_year,
            "qualifies": g.appid in qualifying,
            "english": english.get(g.appid),
            "in_studies": g.appid in studies,
            "tags": list(g.tags),
            "short_description": g.short_description,
            "data_source": g.data_source,
            "reviews_observed_at": g.reviews_observed_at,
            "store_observed_at": g.store_observed_at,
        }
        for g in sorted(games, key=lambda g: g.appid)
    ]


def _estimate(prefix: str, e: Estimate | None) -> Row:
    return {
        f"{prefix}_low": e.low if e else None,
        f"{prefix}_best": e.central() if e else None,
        f"{prefix}_high": e.high if e else None,
        f"{prefix}_confidence": e.confidence if e else None,
    }


@dataclass(frozen=True, slots=True)
class ResearchEntry:
    appid: int
    name: str
    budget: ResearchFindings | None
    budget_at: str | None
    economics: Economics | None
    cost_currency: str
    reviews: ResearchFindings | None
    reviews_at: str | None


def research_rows(entries: Sequence[ResearchEntry]) -> list[Row]:
    rows: list[Row] = []
    for r in sorted(entries, key=lambda r: r.appid):
        b, e, v = r.budget, r.economics, r.reviews
        rows.append(
            {
                "appid": r.appid,
                "name": r.name,
                "studio": b.studio if b else None,
                **_estimate("team_size", b.team_size if b else None),
                **_estimate("development_months", b.development_months if b else None),
                "person_years_best": e.person_years.best if e else None,
                "cost_best": e.cost.best if e else None,
                "cost_currency": r.cost_currency if e else None,
                "cost_usd_best": e.cost_usd.best if e else None,
                "break_even_gross_usd_best": e.break_even_gross_usd.best if e else None,
                "revenue_multiple": e.revenue_multiple if e else None,
                "budget_researched_at": r.budget_at,
                "why_it_worked": [i.point for i in v.why_it_worked] if v else None,
                "what_held_it_back": [i.point for i in v.what_held_it_back] if v else None,
                "reviews_researched_at": r.reviews_at,
            }
        )
    return rows


def review_history_rows(history: Mapping[int, Sequence[ReviewsObservation]]) -> list[Row]:
    return [
        {
            "appid": o.appid,
            "fetched_at": o.fetched_at,
            "total_reviews": o.total_reviews,
            "total_positive": o.total_positive,
            "total_negative": o.total_negative,
        }
        for appid in sorted(history)
        for o in sorted(history[appid], key=lambda o: o.fetched_at)
    ]


def readme(tables: Sequence[Table], exported_at: str, notes: Sequence[str]) -> str:
    lines = [
        "# Steam Study Tool dataset",
        "",
        f"Exported {exported_at} (format version {DATASET_FORMAT_VERSION}).",
        "",
        "Each table is in `csv/<table>.csv` (UTF-8, comma-separated, header row) and in",
        "`json/<table>.json` (a list of objects with the same keys). `appid` joins the tables.",
        "In CSV, an empty cell is an unknown value, booleans are `true`/`false`, and list values",
        "are JSON arrays inside the cell (e.g. `json.loads(cell)` / `JSON.parse(cell)`).",
        "`json/research-details.json` has the full LLM research incl. sources and evidence.",
        "",
        "Revenue, cost, team size and development time are ESTIMATES, not actual figures.",
        "",
        *notes,
    ]
    for t in tables:
        lines += ["", f"## {t.name} ({len(t.rows):,} rows)", "", t.description, ""]
        lines += ["| Column | Meaning |", "|---|---|"]
        lines += [f"| `{c}` | {m} |" for c, m in t.columns]
    return "\n".join(lines) + "\n"
