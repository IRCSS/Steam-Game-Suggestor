"""API contracts for settings, studies, languages, exports and system actions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class LanguageJobView(BaseModel):
    state: Literal["idle", "running", "completed", "cancelled", "failed"]
    scope: str
    total: int
    done: int
    found: int
    unavailable: int
    errors: int
    skipped: int
    started_at: str | None
    finished_at: str | None
    message: str
    recent: list[str]
    seconds_per_request: float


class LanguageStatusResponse(BaseModel):
    total_games: int
    qualified_games: int
    known: int  # games with a known English yes/no
    known_qualified: int
    english: int
    no_english: int
    unavailable: int
    offline: bool
    job: LanguageJobView


class LanguageFetchRequest(BaseModel):
    scope: Literal["qualified", "all"] = "qualified"


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
