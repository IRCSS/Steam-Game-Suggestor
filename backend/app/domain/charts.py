"""Chart aggregates over a slice of the catalog. Pure functions, no I/O.

Rules (plan section 8.2): one row per AppID (the latest observation - never repeated snapshots),
counts always reported with every aggregate, missing values are skipped (never treated as 0),
and everything is an *estimate* scoped to the local catalog - never "all of Steam".
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.models import Game

# 1-2-5 log bins (USD). Revenue is extremely skewed, so linear bins would put almost every game
# in the first bar.
REVENUE_EDGES: tuple[float, ...] = (
    0, 10_000, 20_000, 50_000, 100_000, 200_000, 500_000, 1_000_000, 2_000_000, 5_000_000,
    10_000_000, 20_000_000, 50_000_000, 100_000_000, math.inf,
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Bin:
    start: float
    end: float  # exclusive; inf for the last bin
    count: int


@dataclass(frozen=True, slots=True)
class TagStat:
    tag: str
    count: int
    median_revenue: float
    median_reviews: float
    median_score: float


@dataclass(frozen=True, slots=True)
class YearStat:
    year: int
    count: int
    median_revenue: float


@dataclass(frozen=True, slots=True)
class Kpis:
    count: int
    median_revenue: float | None
    median_price: float | None
    median_reviews: float | None
    median_score: float | None


def median(values: Iterable[float]) -> float | None:
    data = list(values)
    return float(statistics.median(data)) if data else None


def revenue_histogram(games: Sequence[Game]) -> list[Bin]:
    """Counts per log bin; trims empty bins at both ends. Counts always sum to len(games)."""
    counts = [0] * (len(REVENUE_EDGES) - 1)
    for game in games:
        for i in range(len(counts)):
            if REVENUE_EDGES[i] <= game.estimated_revenue < REVENUE_EDGES[i + 1]:
                counts[i] += 1
                break
    bins = [Bin(REVENUE_EDGES[i], REVENUE_EDGES[i + 1], c) for i, c in enumerate(counts)]
    first = next((i for i, b in enumerate(bins) if b.count), None)
    if first is None:
        return []
    last = max(i for i, b in enumerate(bins) if b.count)
    return bins[first : last + 1]


def kpis(games: Sequence[Game]) -> Kpis:
    return Kpis(
        count=len(games),
        median_revenue=median(g.estimated_revenue for g in games),
        median_price=median(g.price for g in games),
        median_reviews=median(g.total_reviews for g in games),
        median_score=median(g.review_score for g in games if g.total_reviews > 0),
    )


def tag_stats(games: Sequence[Game], min_count: int = 20, limit: int = 25) -> list[TagStat]:
    """The `limit` most common tags (with at least `min_count` games), with medians."""
    by_tag: dict[str, list[Game]] = defaultdict(list)
    for game in games:
        for tag in set(game.tags):
            by_tag[tag].append(game)
    common = [t for t, gs in by_tag.items() if len(gs) >= min_count]
    common.sort(key=lambda t: (-len(by_tag[t]), t))
    out: list[TagStat] = []
    for tag in common[:limit]:
        gs = by_tag[tag]
        out.append(
            TagStat(
                tag=tag,
                count=len(gs),
                median_revenue=median(g.estimated_revenue for g in gs) or 0.0,
                median_reviews=median(g.total_reviews for g in gs) or 0.0,
                median_score=median(g.review_score for g in gs) or 0.0,
            )
        )
    return out


def year_stats(games: Sequence[Game]) -> list[YearStat]:
    counts = Counter(g.release_year for g in games)
    return [
        YearStat(
            year=year,
            count=counts[year],
            median_revenue=median(g.estimated_revenue for g in games if g.release_year == year)
            or 0.0,
        )
        for year in sorted(counts)
    ]


def _spread(appid: int) -> int:
    return (appid * 2654435761) % 4294967296  # Knuth multiplicative hash: stable, well spread


def sample(
    games: Sequence[Game], max_points: int, keep: frozenset[int] = frozenset()
) -> list[Game]:
    """Deterministic sample for scatter plots; AppIDs in `keep` (e.g. studies) always included."""
    if len(games) <= max_points:
        return list(games)
    kept = [g for g in games if g.appid in keep]
    rest = sorted((g for g in games if g.appid not in keep), key=lambda g: _spread(g.appid))
    return kept + rest[: max(0, max_points - len(kept))]
