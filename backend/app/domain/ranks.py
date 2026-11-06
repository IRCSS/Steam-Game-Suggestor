"""Yearly revenue ranks over the local catalog.

Reverse-engineered from the legacy dataset and verified against all 15,521 records (0 rank and
0 percentile mismatches):
  * population = games released in the same year with at least 20 reviews
  * rank       = 1-based position by estimated revenue, descending; ties keep source order
  * percentile = round(100 * (N - rank + 1) / N, 2)
So recomputing over untouched legacy data reproduces the legacy values exactly, and refreshed or
newly discovered games are ranked the same way ("local catalog" scope).
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Iterable

from app.domain.models import Game

MIN_REVIEWS_FOR_RANK = 20


def compute_ranks(games: Iterable[Game]) -> list[Game]:
    games = list(games)
    by_year: dict[int, list[Game]] = defaultdict(list)
    for game in games:
        if game.total_reviews >= MIN_REVIEWS_FOR_RANK:
            by_year[game.release_year].append(game)
    ranked: dict[int, tuple[int, int, float]] = {}
    for population in by_year.values():
        population.sort(key=lambda g: (-g.estimated_revenue, g.source_index, g.appid))
        n = len(population)
        for index, game in enumerate(population):
            rank = index + 1
            ranked[game.appid] = (rank, n, round(100 * (n - rank + 1) / n, 2))
    out: list[Game] = []
    for game in games:
        rank, n, pct = ranked.get(game.appid, (0, len(by_year.get(game.release_year, ())), 0.0))
        if (rank, n, pct) == (
            game.revenue_rank_in_year,
            game.qualifying_games_in_year,
            game.revenue_percentile_in_year,
        ):
            out.append(game)
        else:
            out.append(
                dataclasses.replace(
                    game,
                    revenue_rank_in_year=rank,
                    qualifying_games_in_year=n,
                    revenue_percentile_in_year=pct,
                )
            )
    return out
