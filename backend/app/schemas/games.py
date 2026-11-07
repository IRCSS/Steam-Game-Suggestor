"""API response/request contracts for games, suggestions and sessions."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.filters import StudyFilters
from app.domain.languages import LanguageRecord
from app.domain.models import Game
from app.domain.revenue import LEGACY_MODEL_ID, LEGACY_MODEL_LABEL, usd_to_minor_units
from app.importer import LEGACY_SOURCE
from app.storage.studies import Study

SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
SessionId = Annotated[str, Field(pattern=SESSION_ID_PATTERN)]


class Money(BaseModel):
    amount_minor: int
    currency_code: str
    context: str


class Reviews(BaseModel):
    total: int
    positive_percent: float
    observed_at: str | None
    source: str


class RevenueEstimate(BaseModel):
    amount_minor: int
    currency_code: str
    model: str
    label: str


class LegacyRank(BaseModel):
    """Yearly rank over the local catalog (equals the imported legacy rank until data changes)."""

    rank: int
    population_count: int
    percentile: float
    population: str
    scope_label: str
    legacy_rank: int | None = None  # as imported (None for games discovered later)
    legacy_population_count: int | None = None


class Provenance(BaseModel):
    data_source: Literal["legacy_import", "steam", "steam_new"]
    reviews_observed_at: str | None
    store_observed_at: str | None
    tags_observed_at: str | None
    tags_source: str
    release_date: str | None


class Qualification(BaseModel):
    qualified: bool
    threshold_usd: int


class LanguageInfo(BaseModel):
    status: Literal["unknown", "ok", "unavailable"]
    english: bool | None
    languages: list[str]
    fetched_at: str | None

    @classmethod
    def from_record(cls, record: LanguageRecord | None) -> LanguageInfo:
        if record is None:
            return cls(status="unknown", english=None, languages=[], fetched_at=None)
        return cls(
            status=record.status,
            english=record.english,
            languages=list(record.languages),
            fetched_at=record.fetched_at,
        )


class StudyState(BaseModel):
    in_studies: bool
    added_at: str | None
    added_by: str | None


class GameReport(BaseModel):
    appid: int
    name: str
    short_description: str
    release_year: int
    tags: list[str]
    price: Money
    reviews: Reviews
    estimated_revenue: RevenueEstimate
    rank: LegacyRank
    qualification: Qualification
    freshness: str
    steam_url: str
    header_image: str | None  # Steam's artwork URL when known (try first; newer apps need it)
    languages: LanguageInfo
    study: StudyState
    provenance: Provenance

    @classmethod
    def from_game(
        cls,
        game: Game,
        threshold_usd: int,
        language: LanguageRecord | None = None,
        study: Study | None = None,
    ) -> GameReport:
        return cls(
            appid=game.appid,
            name=game.name,
            short_description=game.short_description,
            release_year=game.release_year,
            tags=list(game.tags),
            price=Money(
                amount_minor=usd_to_minor_units(game.price),
                currency_code="USD",
                context=game.price_context,
            ),
            reviews=Reviews(
                total=game.total_reviews,
                positive_percent=game.review_score,
                observed_at=game.reviews_observed_at,
                source=LEGACY_SOURCE
                if game.reviews_observed_at is None
                else "steam_reviews_all_languages",
            ),
            estimated_revenue=RevenueEstimate(
                amount_minor=game.estimated_revenue * 100,
                currency_code="USD",
                model=LEGACY_MODEL_ID,
                label=LEGACY_MODEL_LABEL,
            ),
            rank=LegacyRank(
                rank=game.revenue_rank_in_year,
                population_count=game.qualifying_games_in_year,
                percentile=game.revenue_percentile_in_year,
                population=game.rank_population,
                scope_label=(
                    f"legacy dataset, {game.release_year} releases"
                    if (game.revenue_rank_in_year, game.qualifying_games_in_year)
                    == (game.legacy_rank_in_year, game.legacy_qualifying_games_in_year)
                    else f"local catalog, {game.release_year} releases"
                ),
                legacy_rank=game.legacy_rank_in_year,
                legacy_population_count=game.legacy_qualifying_games_in_year,
            ),
            provenance=Provenance(
                data_source=game.data_source,  # type: ignore[arg-type]
                reviews_observed_at=game.reviews_observed_at,
                store_observed_at=game.store_observed_at,
                tags_observed_at=game.tags_observed_at,
                tags_source=game.tags_source,
                release_date=game.release_date,
            ),
            qualification=Qualification(
                qualified=game.estimated_revenue >= threshold_usd, threshold_usd=threshold_usd
            ),
            freshness=(
                "imported_legacy_unknown_age"
                if game.reviews_observed_at is None
                else f"reviews_as_of_{game.reviews_observed_at[:10]}"
            ),
            steam_url=f"https://store.steampowered.com/app/{game.appid}",
            header_image=game.header_image,
            languages=LanguageInfo.from_record(language),
            study=StudyState(
                in_studies=study is not None,
                added_at=study.added_at if study else None,
                added_by=study.added_by if study else None,
            ),
        )


class GameSummary(BaseModel):
    appid: int
    name: str
    release_year: int
    estimated_revenue_usd: int
    legacy_rank_in_year: int

    @classmethod
    def from_game(cls, game: Game) -> GameSummary:
        return cls(
            appid=game.appid,
            name=game.name,
            release_year=game.release_year,
            estimated_revenue_usd=game.estimated_revenue,
            legacy_rank_in_year=game.revenue_rank_in_year,
        )


class GameSearchResponse(BaseModel):
    items: list[GameSummary]


class StudyFiltersModel(BaseModel):
    """Legacy study filters. ``null`` numeric bound = field left empty (legacy fallback)."""

    years: list[int]
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
    include_tags: str = Field(default="", max_length=2000)
    exclude_tags: str = Field(default="", max_length=2000)
    require_english: bool = Field(
        default=False, description="Exclude games known to have no English support"
    )

    def to_domain(self) -> StudyFilters:
        return StudyFilters(
            years=frozenset(self.years),
            min_revenue=self.min_revenue,
            max_revenue=self.max_revenue,
            min_price=self.min_price,
            max_price=self.max_price,
            min_rank=self.min_rank,
            max_rank=self.max_rank,
            min_percentile=self.min_percentile,
            max_percentile=self.max_percentile,
            min_reviews=self.min_reviews,
            max_reviews=self.max_reviews,
            min_review_score=self.min_review_score,
            max_review_score=self.max_review_score,
            include_tags=self.include_tags,
            exclude_tags=self.exclude_tags,
        )

    @classmethod
    def from_domain(cls, f: StudyFilters) -> StudyFiltersModel:
        return cls(
            years=sorted(f.years),
            min_revenue=f.min_revenue,
            max_revenue=f.max_revenue,
            min_price=f.min_price,
            max_price=f.max_price,
            min_rank=f.min_rank,
            max_rank=f.max_rank,
            min_percentile=f.min_percentile,
            max_percentile=f.max_percentile,
            min_reviews=f.min_reviews,
            max_reviews=f.max_reviews,
            min_review_score=f.min_review_score,
            max_review_score=f.max_review_score,
            include_tags=f.include_tags,
            exclude_tags=f.exclude_tags,
        )


class SuggestionQuery(BaseModel):
    session_id: SessionId
    filters: StudyFiltersModel
    avoid_repeats: bool = True
    include_below_threshold: bool = False
    exclude_studies: bool = Field(default=True, description="Skip games already in Studies")


class SuggestionRequest(SuggestionQuery):
    seed: int | None = Field(default=None, description="Deterministic RNG seed (tests/debugging)")


class SuggestionResponse(BaseModel):
    status: Literal["ok", "no_matches"]
    game: GameReport | None
    repeat_history_reset: bool
    candidate_count: int


class CountResponse(BaseModel):
    count: int
    count_ignoring_history: int
    all_seen: bool


class ViewRequest(BaseModel):
    appid: int


class HistoryResponse(BaseModel):
    items: list[GameSummary]


class DatasetInfo(BaseModel):
    total_games: int
    qualified_games: int
    qualification_threshold_usd: int
    year_counts: dict[str, int]
    source_sha256: str | None
    imported_at: str | None
    scope_label: str
    revenue_model: str
    revenue_model_label: str


class MetaResponse(BaseModel):
    dataset: DatasetInfo
    years: list[int]
    tags: list[str]
    default_filters: StudyFiltersModel
    default_avoid_repeats: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "needs_import"]
    version: str
    schema_version: int
    games: int
    message: str | None = None
