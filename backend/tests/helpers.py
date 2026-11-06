from __future__ import annotations

import dataclasses

from app.domain.filters import StudyFilters
from app.domain.models import LegacyGame

ALL_YEARS = frozenset({2022, 2023, 2024, 2025})


def game(**overrides: object) -> LegacyGame:
    base: dict[str, object] = {
        "appid": 1,
        "name": "Test Game",
        "short_description": "",
        "tags": ("Indie", "Colony Sim", "Roguelike Deckbuilder"),
        "release_year": 2023,
        "price": 10.0,
        "total_reviews": 500,
        "review_score": 90.0,
        "estimated_revenue": 225_000,
        "revenue_rank_in_year": 500,
        "qualifying_games_in_year": 4244,
        "revenue_percentile_in_year": 88.2,
    }
    base.update(overrides)
    return LegacyGame(**base)  # type: ignore[arg-type]


def open_filters(**overrides: object) -> StudyFilters:
    """All bounds empty (legacy fallbacks) and all years selected."""
    return dataclasses.replace(StudyFilters(years=ALL_YEARS), **overrides)  # type: ignore[arg-type]
