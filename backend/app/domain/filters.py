"""Study filters - a faithful port of the legacy `filteredGames()` semantics.

Legacy rules preserved:
* Every numeric bound is inclusive. An empty/missing bound falls back to the legacy default
  (min revenue 0, max +inf, min price 0, max +inf, min rank 1, max +inf, percentile 0..100,
  min reviews 20 (!), max +inf, review score 0..100).
* Release year must be one of the selected years (an empty selection matches nothing).
* Tag inputs are comma separated, trimmed, lower-cased. Required tags are AND-combined,
  excluded tags OR-combined; a filter tag matches a game tag when equal or a substring of it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.models import Game

INF = math.inf


@dataclass(frozen=True, slots=True)
class StudyFilters:
    """User-visible study filters. ``None`` means "field left empty" (legacy fallback applies)."""

    years: frozenset[int]
    min_revenue: float | None = None
    max_revenue: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_rank: float | None = None
    max_rank: float | None = None
    min_percentile: float | None = None
    max_percentile: float | None = None
    min_reviews: float | None = None
    max_reviews: float | None = None
    min_review_score: float | None = None
    max_review_score: float | None = None
    include_tags: str = ""
    exclude_tags: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedBounds:
    years: frozenset[int]
    min_revenue: float
    max_revenue: float
    min_price: float
    max_price: float
    min_rank: float
    max_rank: float
    min_percentile: float
    max_percentile: float
    min_reviews: float
    max_reviews: float
    min_review_score: float
    max_review_score: float
    required_tags: tuple[str, ...]
    excluded_tags: tuple[str, ...]


def legacy_default_filters(years: Iterable[int], max_rank: int) -> StudyFilters:
    """Defaults set by the legacy HTML inputs and `resetFilters()`."""
    return StudyFilters(
        years=frozenset(years),
        min_revenue=150_000,
        max_revenue=800_000,
        min_price=0,
        max_price=200,
        min_rank=1,
        max_rank=max_rank,
        min_percentile=0,
        max_percentile=100,
        min_reviews=20,
        max_reviews=None,
        min_review_score=50,
        max_review_score=100,
        include_tags="",
        exclude_tags="",
    )


def parse_tags(value: str | None) -> tuple[str, ...]:
    """Legacy `parseTags`: split on commas, trim, lower-case, drop empties."""
    return tuple(t for t in (part.strip().lower() for part in str(value or "").split(",")) if t)


def display_tags(value: str | None) -> tuple[str, ...]:
    """Legacy `displayTags`: split on commas, trim, keep case, drop empties."""
    return tuple(t for t in (part.strip() for part in str(value or "").split(",")) if t)


def _bound(value: float | None, fallback: float) -> float:
    if value is None or not math.isfinite(value):
        return fallback
    return value


def resolve(filters: StudyFilters) -> ResolvedBounds:
    return ResolvedBounds(
        years=filters.years,
        min_revenue=_bound(filters.min_revenue, 0),
        max_revenue=_bound(filters.max_revenue, INF),
        min_price=_bound(filters.min_price, 0),
        max_price=_bound(filters.max_price, INF),
        min_rank=_bound(filters.min_rank, 1),
        max_rank=_bound(filters.max_rank, INF),
        min_percentile=_bound(filters.min_percentile, 0),
        max_percentile=_bound(filters.max_percentile, 100),
        min_reviews=_bound(filters.min_reviews, 20),
        max_reviews=_bound(filters.max_reviews, INF),
        min_review_score=_bound(filters.min_review_score, 0),
        max_review_score=_bound(filters.max_review_score, 100),
        required_tags=parse_tags(filters.include_tags),
        excluded_tags=parse_tags(filters.exclude_tags),
    )


def _tag_hit(filter_tag: str, game_tags_lower: Sequence[str]) -> bool:
    # Legacy: `tag === required || tag.includes(required)` (equality is implied by includes).
    return any(filter_tag in tag for tag in game_tags_lower)


def matches(game: Game, b: ResolvedBounds) -> bool:
    if game.release_year not in b.years:
        return False
    if not (b.min_revenue <= game.estimated_revenue <= b.max_revenue):
        return False
    if not (b.min_price <= game.price <= b.max_price):
        return False
    if not (b.min_rank <= game.revenue_rank_in_year <= b.max_rank):
        return False
    if not (b.min_percentile <= game.revenue_percentile_in_year <= b.max_percentile):
        return False
    if not (b.min_reviews <= game.total_reviews <= b.max_reviews):
        return False
    if not (b.min_review_score <= game.review_score <= b.max_review_score):
        return False
    tags = game.tags_lower
    if not all(_tag_hit(req, tags) for req in b.required_tags):
        return False
    return not any(_tag_hit(exc, tags) for exc in b.excluded_tags)


def filter_games(
    games: Iterable[Game],
    filters: StudyFilters,
    exclude_appids: frozenset[int] | set[int] = frozenset(),
) -> list[Game]:
    """Return matching games in input order, skipping any AppID in ``exclude_appids``."""
    bounds = resolve(filters)
    return [g for g in games if g.appid not in exclude_appids and matches(g, bounds)]
