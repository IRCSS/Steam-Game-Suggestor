"""Domain records. Pure data - no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field

LEGACY_POPULATION_PREFIX = "legacy_dataset_qualifying_games_"


@dataclass(frozen=True, slots=True)
class LegacyGame:
    """One game from the imported legacy 2022-2025 snapshot, with values exactly as imported."""

    appid: int
    name: str
    short_description: str
    tags: tuple[str, ...]  # trimmed, non-empty (legacy `normalizedTags`)
    release_year: int
    price: float  # legacy listed price, USD-like, capture context unknown
    total_reviews: int
    review_score: float
    estimated_revenue: int  # legacy estimate (reviews x 45 x price), USD
    revenue_rank_in_year: int
    qualifying_games_in_year: int
    revenue_percentile_in_year: float
    source_index: int = 0  # position in the original JSON array (keeps legacy ordering)
    tags_lower: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not self.tags_lower and self.tags:
            object.__setattr__(self, "tags_lower", tuple(t.lower() for t in self.tags))

    @property
    def legacy_population(self) -> str:
        return f"{LEGACY_POPULATION_PREFIX}{self.release_year}"


def normalize_tags(raw_tags: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Legacy `normalizedTags`: String(tag).trim(), dropping empty values. Order preserved."""
    return tuple(t for t in (str(tag).strip() for tag in raw_tags) if t)
