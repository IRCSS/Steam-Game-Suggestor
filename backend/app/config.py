"""Local configuration. Values come from environment variables (optionally a .env file).

No secrets are needed for Phase 0/1. Future provider keys must only be read here, on the
server, and never returned by any API route.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_VERSION = "0.1.0"

DEFAULT_DB_PATH = REPO_ROOT / ".local" / "steam_study.sqlite3"
DEFAULT_LOG_DIR = REPO_ROOT / ".local" / "logs"
REFERENCE_HTML = REPO_ROOT / "reference" / "steam_game_suggester.html"
REFERENCE_SHA256 = "bdc25ab3d24ae0397119b427f1aaead1faf6081ae315c0d686e6896199711d88"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing environment variables win."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _resolve(path_value: str | None, default: Path) -> Path:
    if not path_value:
        return default
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    log_dir: Path | None
    qualification_min_revenue_usd: int


def load_settings() -> Settings:
    _load_dotenv(REPO_ROOT / ".env")
    return Settings(
        db_path=_resolve(os.environ.get("STEAM_STUDY_DB"), DEFAULT_DB_PATH),
        log_dir=_resolve(os.environ.get("STEAM_STUDY_LOG_DIR"), DEFAULT_LOG_DIR),
        qualification_min_revenue_usd=int(
            os.environ.get("STEAM_STUDY_QUALIFICATION_MIN_REVENUE_USD", "100000")
        ),
    )
