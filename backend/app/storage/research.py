"""Research results: one JSON file per game in ``<data>/research/<appid>.json`` (shared drive safe).

Each file keeps the last few runs (newest last; budget and review runs mixed), so a refresh never
loses the previous answer. Only the validated findings and run metadata are stored - never review
text.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.research import (
    KIND_COVERS,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ResearchFindings,
    ResearchKind,
    RunKind,
)
from app.logging_config import get_logger
from app.storage.files import atomic_write_json

log = get_logger("research")
KEEP_RUNS = 10


class ResearchRun(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = SCHEMA_VERSION
    prompt_version: str = PROMPT_VERSION
    kind: RunKind = "full"  # runs saved before budget/reviews were split did both
    appid: int
    name: str
    created_at: str
    created_by: str
    provider: str = "claude_code_cli"
    model: str = ""
    cost_usd: float | None = None
    duration_seconds: float = 0
    web_searches: int = 0
    reviews_used: dict[str, int] = Field(default_factory=dict[str, int])
    warnings: list[str] = Field(default_factory=list[str])
    findings: ResearchFindings


class ResearchFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    appid: int
    runs: list[ResearchRun] = Field(default_factory=list[ResearchRun])

    def latest(self, kind: ResearchKind) -> ResearchRun | None:
        """Newest run that answers ``kind`` (a pre-split "full" run answers both)."""
        return next((r for r in reversed(self.runs) if r.kind in KIND_COVERS[kind]), None)


class ResearchStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()

    def _path(self, appid: int) -> Path:
        return self.folder / f"{appid}.json"

    def load(self, appid: int) -> ResearchFile | None:
        path = self._path(appid)
        if not path.is_file():
            return None
        try:
            return ResearchFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ValidationError) as exc:
            log.warning("unreadable research file", extra={"file": str(path), "err": repr(exc)})
            return None

    def latest(self, appid: int, kind: ResearchKind) -> ResearchRun | None:
        record = self.load(appid)
        return record.latest(kind) if record else None

    def add(self, run: ResearchRun) -> None:
        with self._lock:
            record = self.load(run.appid) or ResearchFile(appid=run.appid)
            record.runs = [*record.runs, run][-KEEP_RUNS:]
            atomic_write_json(self._path(run.appid), record.model_dump())
        log.info("research saved", extra={"appid": run.appid, "cost_usd": run.cost_usd})

    def appids(self) -> frozenset[int]:
        if not self.folder.is_dir():
            return frozenset()
        out: set[int] = set()
        for path in self.folder.glob("*.json"):
            if path.stem.isdigit():
                out.add(int(path.stem))
        return frozenset(out)
