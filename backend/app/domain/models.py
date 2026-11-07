"""Domain records. Pure data - no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field

LEGACY_POPULATION_PREFIX = "legacy_dataset_qualifying_games_"
CATALOG_POPULATION_PREFIX = "local_catalog_games_"


@dataclass(frozen=True, slots=True)
class Game:
    """One game in the local catalog: the imported legacy snapshot, optionally overlaid with newer
    Steam observations (see ``domain/catalog.py``).

    ``revenue_rank_in_year`` / ``qualifying_games_in_year`` / ``revenue_percentile_in_year`` are
    computed over the local catalog (``domain/ranks.py``). For unchanged legacy data they equal the
    imported legacy values exactly; the originals are kept in the ``legacy_*`` fields.
    """

    appid: int
    name: str
    short_description: str
    tags: tuple[str, ...]  # trimmed, non-empty (legacy `normalizedTags`)
    release_year: int
    price: float  # USD; legacy listed price, or Steam's undiscounted price after a refresh
    total_reviews: int
    review_score: float
    estimated_revenue: int  # estimate (reviews x 45 x price), USD
    revenue_rank_in_year: int
    qualifying_games_in_year: int
    revenue_percentile_in_year: float
    source_index: int = 0  # position in the original JSON array (keeps legacy ordering)
    tags_lower: tuple[str, ...] = field(default=(), compare=False)
    # --- provenance (defaults describe an untouched legacy record) --------------------------
    data_source: str = "legacy_import"  # legacy_import | steam (overlay) | steam_new (not legacy)
    reviews_observed_at: str | None = None  # None = legacy, capture date unknown
    store_observed_at: str | None = None
    tags_observed_at: str | None = None
    tags_source: str = "legacy_import"
    price_context: str = "legacy_price_context_unknown"
    release_date: str | None = None
    is_free: bool | None = None
    header_image: str | None = None  # Steam's artwork URL from the store; None = derive from AppID
    legacy_rank_in_year: int | None = None
    legacy_qualifying_games_in_year: int | None = None
    legacy_revenue_percentile_in_year: float | None = None

    def __post_init__(self) -> None:
        if not self.tags_lower and self.tags:
            object.__setattr__(self, "tags_lower", tuple(t.lower() for t in self.tags))

    @property
    def is_legacy_unchanged(self) -> bool:
        return self.data_source == "legacy_import"

    @property
    def legacy_population(self) -> str:
        return f"{LEGACY_POPULATION_PREFIX}{self.release_year}"

    @property
    def rank_population(self) -> str:
        return f"{CATALOG_POPULATION_PREFIX}{self.release_year}"


def normalize_tags(raw_tags: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Legacy `normalizedTags`: String(tag).trim(), dropping empty values. Order preserved."""
    return tuple(t for t in (str(tag).strip() for tag in raw_tags) if t)
