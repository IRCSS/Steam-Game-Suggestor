"""Studies: games the user archived as potential case studies.

One JSON file per game in ``<data>/studies/<appid>.json``. Different PCs adding different games
never touch the same file, which keeps this safe on shared or cloud-synced drives. The file is
the long-term home for everything about a study (notes and LLM research will be added here).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.db.connection import utc_now
from app.logging_config import get_logger
from app.storage.files import atomic_write_json, machine_id

log = get_logger("studies")
CACHE_SECONDS = 5.0


class Study(BaseModel):
    model_config = ConfigDict(extra="allow")  # keep fields written by newer versions

    schema_version: int = 1
    appid: int
    name: str
    status: str = "study"
    added_at: str
    added_by: str
    updated_at: str
    notes: str = ""
    research: dict[str, Any] | None = None  # filled by "Get more info from LLM" (later)


class StudyStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()
        self._cache: dict[int, Study] | None = None
        self._loaded_at = 0.0

    def _path(self, appid: int) -> Path:
        return self.folder / f"{appid}.json"

    def _load(self) -> dict[int, Study]:
        studies: dict[int, Study] = {}
        if not self.folder.is_dir():
            return studies
        for path in self.folder.glob("*.json"):
            try:
                study = Study.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, ValidationError) as exc:
                log.warning(
                    "skipping unreadable study file", extra={"file": str(path), "err": repr(exc)}
                )
                continue
            studies[study.appid] = study
        return studies

    def all(self) -> dict[int, Study]:
        """All studies; re-read at most every few seconds to pick up other PCs' changes."""
        with self._lock:
            if self._cache is None or time.monotonic() - self._loaded_at > CACHE_SECONDS:
                self._cache = self._load()
                self._loaded_at = time.monotonic()
            return dict(self._cache)

    def appids(self) -> frozenset[int]:
        return frozenset(self.all())

    def get(self, appid: int) -> Study | None:
        return self.all().get(appid)

    def add(self, appid: int, name: str) -> Study:
        existing = self.get(appid)
        if existing is not None:
            return existing
        now = utc_now()
        study = Study(appid=appid, name=name, added_at=now, added_by=machine_id(), updated_at=now)
        with self._lock:
            atomic_write_json(self._path(appid), study.model_dump())
            if self._cache is not None:
                self._cache[appid] = study
        log.info("study added", extra={"appid": appid})
        return study

    def remove(self, appid: int) -> bool:
        with self._lock:
            path = self._path(appid)
            removed = path.exists()
            path.unlink(missing_ok=True)
            if self._cache is not None:
                self._cache.pop(appid, None)
        if removed:
            log.info("study removed", extra={"appid": appid})
        return removed
