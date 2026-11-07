"""Configuration: a `settings.json` next to the app, editable from the in-app Settings dialog.

App folder (where settings.json lives):
  * packaged exe -> the folder containing SteamStudyTool.exe (may be a shared drive)
  * development  -> <repo>/.local
  * override     -> environment variable STEAM_STUDY_APP_DIR (tests, e2e, smoke test)

Relative paths inside settings.json are resolved against the app folder, so the whole folder can
be copied or shared (e.g. on G:). If settings.json is missing it is created with defaults; if it
is unreadable it is set aside (settings.invalid-<time>.json) and defaults are written.

Secrets (future Steam / LLM keys) are stored in settings.json in plain text, are only ever read
on the server, and are never returned by an API route (only "is set" flags are).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.research import CostModel

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_VERSION = "0.6.0"
SETTINGS_FILE_NAME = "settings.json"
SETTINGS_VERSION = 2
CATALOG_FILE_NAME = "catalog.sqlite3"

REFERENCE_HTML = REPO_ROOT / "reference" / "steam_game_suggester.html"
REFERENCE_SHA256 = "bdc25ab3d24ae0397119b427f1aaead1faf6081ae315c0d686e6896199711d88"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader for development (KEY=VALUE lines). Existing variables win."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def default_app_dir() -> Path:
    override = os.environ.get("STEAM_STUDY_APP_DIR")
    if override:
        return Path(override).resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return REPO_ROOT / ".local"


# --- settings.json schema --------------------------------------------------------------------


class SteamSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_key: str = ""  # Phase 3+ (Steamworks Web API); not used yet
    store_requests_per_minute: int = Field(default=35, ge=1, le=120)


class LlmSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    # "claude_code" = the Claude Code CLI installed on this PC (headless). Others: future.
    provider: Literal["claude_code", "none", "openai", "anthropic"] = "claude_code"
    model: str = ""  # empty = the CLI's default model
    api_key: str = ""  # only for future API providers
    claude_cli_path: str = ""  # empty = auto-detect
    max_budget_usd: float = Field(default=2.0, ge=0.1, le=50)
    timeout_minutes: int = Field(default=15, ge=2, le=120)


class CostModelSettings(BaseModel):
    """How research turns team size x development time into money (user-editable)."""

    model_config = ConfigDict(extra="allow")

    salary_per_person_year: float = Field(default=50_000, gt=0)
    salary_currency: str = Field(default="EUR", max_length=8)
    usd_per_salary_unit: float = Field(default=1.08, gt=0)  # EUR -> USD
    comparison_team_size: int = Field(default=3, ge=1, le=1000)
    platform_cut: float = Field(default=0.30, ge=0, lt=1)


class SettingsFile(BaseModel):
    """Exact content of settings.json. Unknown keys are preserved (forward compatibility)."""

    model_config = ConfigDict(extra="allow")

    version: int = SETTINGS_VERSION
    data_dir: str = "data"
    export_dir: str = "studiesJPG"
    qualification_min_revenue_usd: int = Field(default=100_000, ge=0)
    offline_mode: bool = False
    steam: SteamSettings = Field(default_factory=SteamSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    cost_model: CostModelSettings = Field(default_factory=CostModelSettings)


def migrate_settings(content: SettingsFile) -> bool:
    """Upgrade older settings files in place. Returns True when something changed."""
    changed = False
    if content.version < 2:
        # v1 wrote llm.provider = "none" as a placeholder ("not used yet"), not as a user choice.
        if content.llm.provider == "none":
            content.llm.provider = "claude_code"
        content.version = 2
        changed = True
    return changed


def settings_path(app_dir: Path) -> Path:
    return app_dir / SETTINGS_FILE_NAME


def write_settings_file(app_dir: Path, content: SettingsFile) -> None:
    app_dir.mkdir(parents=True, exist_ok=True)
    target = settings_path(app_dir)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(content.model_dump(), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def read_settings_file(app_dir: Path) -> tuple[SettingsFile, str | None]:
    """Return (settings, warning). Creates the file with defaults when it does not exist."""
    path = settings_path(app_dir)
    if not path.exists():
        content = SettingsFile()
        write_settings_file(app_dir, content)
        return content, None
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8-sig"))
        content = SettingsFile.model_validate(raw)
        if migrate_settings(content):
            write_settings_file(app_dir, content)
        return content, None
    except (OSError, ValueError, ValidationError) as exc:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"settings.invalid-{stamp}.json")
        try:
            os.replace(path, backup)
        except OSError:
            backup = path
        content = SettingsFile()
        write_settings_file(app_dir, content)
        return (
            content,
            f"settings.json was invalid ({exc.__class__.__name__}); saved as "
            f"{backup.name} and replaced with defaults.",
        )


def resolve_path(app_dir: Path, value: str) -> Path:
    path = Path(os.path.expandvars(value)).expanduser()
    return path if path.is_absolute() else app_dir / path


# --- runtime settings ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Settings:
    app_dir: Path
    data_dir: Path
    export_dir: Path
    qualification_min_revenue_usd: int = 100_000
    offline: bool = False
    log_dir: Path | None = None
    steam_requests_per_minute: int = 35
    catalog_immutable: bool = False  # packaged app: no SQLite locking on shared drives
    warning: str | None = None
    llm_provider: str = "claude_code"
    llm_model: str = ""
    claude_cli_path: str = ""
    llm_max_budget_usd: float = 2.0
    llm_timeout_minutes: int = 15
    cost_model: CostModel = field(default_factory=CostModel)

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / CATALOG_FILE_NAME

    @property
    def studies_dir(self) -> Path:
        return self.data_dir / "studies"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def research_dir(self) -> Path:
        return self.data_dir / "research"


def settings_from_file(
    app_dir: Path, content: SettingsFile, warning: str | None = None
) -> Settings:
    data_dir = resolve_path(app_dir, content.data_dir)
    return Settings(
        app_dir=app_dir,
        data_dir=data_dir,
        export_dir=resolve_path(app_dir, content.export_dir),
        qualification_min_revenue_usd=content.qualification_min_revenue_usd,
        offline=content.offline_mode or os.environ.get("STEAM_STUDY_OFFLINE") == "1",
        log_dir=data_dir / "logs",
        steam_requests_per_minute=content.steam.store_requests_per_minute,
        catalog_immutable=is_frozen(),
        warning=warning,
        llm_provider=content.llm.provider,
        llm_model=content.llm.model,
        claude_cli_path=content.llm.claude_cli_path,
        llm_max_budget_usd=content.llm.max_budget_usd,
        llm_timeout_minutes=content.llm.timeout_minutes,
        cost_model=CostModel(
            salary_per_person_year=content.cost_model.salary_per_person_year,
            salary_currency=content.cost_model.salary_currency,
            usd_per_salary_unit=content.cost_model.usd_per_salary_unit,
            comparison_team_size=content.cost_model.comparison_team_size,
            platform_cut=content.cost_model.platform_cut,
        ),
    )


def load_settings(app_dir: Path | None = None) -> Settings:
    if not is_frozen():
        _load_dotenv(REPO_ROOT / ".env")
    app_dir = (app_dir or default_app_dir()).resolve()
    content, warning = read_settings_file(app_dir)
    return settings_from_file(app_dir, content, warning)
