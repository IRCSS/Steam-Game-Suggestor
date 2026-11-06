"""API contracts for settings, studies, languages, exports and system actions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.games import StudyFiltersModel

# --- settings ---------------------------------------------------------------------------------


class SettingsView(BaseModel):
    """What the Settings dialog shows. Secrets are never returned - only whether they are set."""

    app_dir: str
    settings_file: str
    data_dir: str  # as written in settings.json (may be relative)
    data_dir_resolved: str
    export_dir: str
    export_dir_resolved: str
    qualification_min_revenue_usd: int
    offline_mode: bool
    offline_forced: bool  # STEAM_STUDY_OFFLINE=1 (tests) overrides the setting
    steam_api_key_set: bool
    steam_store_requests_per_minute: int
    llm_provider: Literal["none", "openai", "anthropic"]
    llm_model: str
    llm_api_key_set: bool
    warning: str | None


class SettingsUpdate(BaseModel):
    data_dir: str = Field(min_length=1, max_length=500)
    export_dir: str = Field(min_length=1, max_length=500)
    qualification_min_revenue_usd: int = Field(ge=0, le=10_000_000_000)
    offline_mode: bool
    steam_store_requests_per_minute: int = Field(ge=1, le=120)
    llm_provider: Literal["none", "openai", "anthropic"]
    llm_model: str = Field(default="", max_length=200)
    # None = keep the stored value; "" = clear it.
    steam_api_key: str | None = Field(default=None, max_length=500)
    llm_api_key: str | None = Field(default=None, max_length=500)


# --- studies ----------------------------------------------------------------------------------


class StudyItem(BaseModel):
    appid: int
    name: str
    added_at: str
    added_by: str
    release_year: int | None
    estimated_revenue_usd: int | None


class StudiesResponse(BaseModel):
    items: list[StudyItem]
    folder: str


# --- languages --------------------------------------------------------------------------------


class LanguageStatusResponse(BaseModel):
    total_games: int
    qualified_games: int
    known: int  # games with a known English yes/no
    known_qualified: int
    english: int
    no_english: int
    unavailable: int
    offline: bool


# --- data jobs --------------------------------------------------------------------------------

Part = Literal["reviews", "store", "tags"]


class RefreshOptions(BaseModel):
    scope: Literal["qualified", "all", "studies"] = "qualified"
    years: list[int] = Field(default_factory=list[int], description="Empty = all years")
    min_revenue_usd: int | None = Field(default=None, ge=0, description="None = catalog floor")
    parts: list[Part] = Field(default_factory=lambda: ["reviews", "store"], min_length=1)
    stale_days: int = Field(default=7, ge=0, le=3650)
    only_missing_languages: bool = False
    limit: int | None = Field(default=None, ge=1)


class DiscoverOptions(BaseModel):
    max_new: int = Field(default=500, ge=1, le=100_000)
    fetch_tags: bool = True
    min_revenue_usd: int | None = Field(default=None, ge=0)
    recheck_unreleased: bool = Field(
        default=True, description="Also re-check recently listed games that were not released"
    )
    max_recheck: int = Field(default=200, ge=0, le=100_000)


class DeepCheckOptions(BaseModel):
    changed_since_days: int = Field(default=365, ge=1, le=3650)
    recheck_set_aside: bool = True
    min_age_days: int = Field(default=30, ge=0, le=3650)
    max_apps: int | None = Field(default=None, ge=1)
    fetch_tags: bool = True


class JobRequest(BaseModel):
    kind: Literal["refresh", "discover", "deep_check", "languages", "app"]
    refresh: RefreshOptions | None = None
    discover: DiscoverOptions | None = None
    deep_check: DeepCheckOptions | None = None
    appid: int | None = Field(default=None, ge=1)
    label: str | None = Field(default=None, max_length=100)


class JobPreview(BaseModel):
    items: int
    requests: int
    seconds: float
    needs_key: bool
    notes: list[str]


class JobView(BaseModel):
    job_id: str
    kind: str
    label: str
    state: Literal["idle", "running", "completed", "cancelled", "failed"]
    total: int
    done: int
    counters: dict[str, int]
    requests: int
    started_at: str | None
    finished_at: str | None
    eta_seconds: float | None
    message: str
    recent: list[str]


class ShardInfo(BaseModel):
    file: str
    bytes: int


class DataStatus(BaseModel):
    data_dir: str
    total_games: int
    qualified_games: int
    legacy_unchanged: int
    refreshed: int
    discovered: int
    years: dict[str, int]
    last_update: str | None
    discovery_cursor_appid: int
    listed_not_screened: int
    set_aside_unreleased: int  # screened, not released / no reviews yet
    set_aside_below_floor: int  # screened, released, but could not reach the floor
    last_deep_check: str | None
    languages_known: int
    steam_api_key_set: bool
    offline: bool
    qualification_threshold_usd: int
    observation_files: list[ShardInfo]
    seconds_per_request: dict[str, float]
    job: JobView


class KeyTestResult(BaseModel):
    ok: bool
    message: str


# --- exports & system -------------------------------------------------------------------------


class JpegExportRequest(BaseModel):
    appid: int
    image_base64: str = Field(max_length=21_000_000)


class JpegExportResponse(BaseModel):
    path: str
    file_name: str
    folder: str


class OpenFolderRequest(BaseModel):
    target: Literal["data", "export", "app"]


# --- charts -----------------------------------------------------------------------------------


class ChartsRequest(BaseModel):
    use_study_filters: bool = False
    filters: StudyFiltersModel | None = None
    include_below_threshold: bool = False
    years: list[int] = Field(default_factory=list[int])
    min_tag_count: int = Field(default=20, ge=1, le=10_000)
    tag_limit: int = Field(default=20, ge=1, le=100)


class KpiView(BaseModel):
    count: int
    median_revenue: float | None
    median_price: float | None
    median_reviews: float | None
    median_score: float | None


class ChartBin(BaseModel):
    start: float
    end: float | None  # None = open-ended last bin
    count: int


class ChartPoint(BaseModel):
    appid: int
    name: str
    year: int
    price: float
    revenue: int
    reviews: int
    score: float
    in_studies: bool


class ChartTag(BaseModel):
    tag: str
    count: int
    median_revenue: float
    median_reviews: float
    median_score: float


class ChartYear(BaseModel):
    year: int
    count: int
    median_revenue: float


class ChartsResponse(BaseModel):
    scope_label: str
    as_of: str
    catalog_total: int
    kpis: KpiView
    revenue_bins: list[ChartBin]
    points: list[ChartPoint]
    points_total: int
    tags: list[ChartTag]
    years: list[ChartYear]
    revenue_model: str


class HistoryPoint(BaseModel):
    observed_at: str | None  # None = legacy import, capture date unknown
    source: str
    total_reviews: int
    estimated_revenue: int


class HistoryResponseModel(BaseModel):
    appid: int
    name: str
    points: list[HistoryPoint]
    enough_history: bool
