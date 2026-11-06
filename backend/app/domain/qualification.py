"""Catalog qualification: which games enter the suggestion pool at all.

This is separate from the user-visible study filters. The default floor is an *estimated* gross
revenue of USD 100,000. Games below the floor stay in the database and remain reachable through
exact lookup; ``include_below_threshold`` turns on a broader exploration mode.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.models import LegacyGame

DEFAULT_MIN_REVENUE_USD = 100_000


@dataclass(frozen=True, slots=True)
class CatalogPolicy:
    min_estimated_revenue_usd: int = DEFAULT_MIN_REVENUE_USD
    include_below_threshold: bool = False


def is_qualified(game: LegacyGame, policy: CatalogPolicy) -> bool:
    # Legacy price-0 games carry estimated_revenue 0; they are below the floor, which is NOT a
    # claim that they earned nothing (F2P income is unknown). See docs/revenue-model.md.
    return game.estimated_revenue >= policy.min_estimated_revenue_usd


def qualify(games: Iterable[LegacyGame], policy: CatalogPolicy) -> list[LegacyGame]:
    if policy.include_below_threshold:
        return list(games)
    return [g for g in games if is_qualified(g, policy)]
