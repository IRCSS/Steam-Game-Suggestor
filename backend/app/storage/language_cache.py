"""Cache of Steam store language lookups, shared by all PCs using the same data folder.

Each PC appends only to its own file ``<data>/cache/languages-<pc>.jsonl`` (one JSON object per
line), so concurrent PCs never write the same file. Reading merges every shard; for the same
AppID the most recent ``fetched_at`` wins. Other PCs' shards are re-read when their size changes.
"""

from __future__ import annotations

import contextlib
import json
import threading
from pathlib import Path

from app.domain.languages import LanguageRecord
from app.logging_config import get_logger
from app.storage.files import machine_id

log = get_logger("languages")


class LanguageCache:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.own_file = folder / f"languages-{machine_id()}.jsonl"
        self._lock = threading.Lock()
        self._records: dict[int, LanguageRecord] = {}
        self._sizes: dict[Path, int] = {}

    def _merge(self, record: LanguageRecord) -> None:
        current = self._records.get(record.appid)
        if current is None or record.fetched_at >= current.fetched_at:
            self._records[record.appid] = record

    def refresh(self) -> None:
        """Re-read shards that changed since the last read."""
        if not self.folder.is_dir():
            return
        with self._lock:
            for path in self.folder.glob("languages-*.jsonl"):
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if self._sizes.get(path) == size:
                    continue
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except OSError as exc:
                    log.warning(
                        "cannot read language shard", extra={"file": str(path), "err": repr(exc)}
                    )
                    continue
                for line in lines:
                    try:
                        raw = json.loads(line)
                        self._merge(
                            LanguageRecord(
                                appid=int(raw["appid"]),
                                status=raw["status"],
                                languages=tuple(raw.get("languages") or ()),
                                fetched_at=str(raw["fetched_at"]),
                                source=str(raw.get("source", "steam_store_appdetails")),
                            )
                        )
                    except (ValueError, KeyError, TypeError):
                        continue  # a partially synced / truncated last line
                self._sizes[path] = size

    def records(self) -> dict[int, LanguageRecord]:
        self.refresh()
        with self._lock:
            return dict(self._records)

    def append(self, record: LanguageRecord) -> None:
        line = json.dumps(
            {
                "appid": record.appid,
                "status": record.status,
                "languages": list(record.languages),
                "fetched_at": record.fetched_at,
                "source": record.source,
            },
            ensure_ascii=False,
        )
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            with self.own_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._merge(record)
            with contextlib.suppress(OSError):
                self._sizes[self.own_file] = self.own_file.stat().st_size
