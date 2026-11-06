"""Steam observations shared through the data folder (safe for several PCs at once).

Each PC appends only to its own file ``<data>/observations/steam-<pc>.jsonl``. Reading merges all
shards incrementally (only newly appended bytes are parsed; a half-synced last line is left for
the next read). The newest observation per (kind, appid) wins; review snapshots are also kept as a
history for the per-game trend chart.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.domain.observations import (
    ListedApp,
    ReviewsObservation,
    StoreObservation,
    SyncMarker,
    TagsObservation,
)
from app.logging_config import get_logger
from app.storage.files import machine_id

log = get_logger("observations")
REFRESH_SECONDS = 3.0
Observation = StoreObservation | ReviewsObservation | TagsObservation | ListedApp | SyncMarker
_KINDS: dict[str, type[Any]] = {
    "store": StoreObservation,
    "reviews": ReviewsObservation,
    "tags": TagsObservation,
    "listed": ListedApp,
    "marker": SyncMarker,
}
_KIND_OF: dict[type[Any], str] = {cls: kind for kind, cls in _KINDS.items()}


def _decode(raw: dict[str, Any]) -> Observation | None:
    cls = _KINDS.get(str(raw.pop("kind", "")))
    if cls is None:
        return None
    if "languages" in raw:
        raw["languages"] = tuple(raw["languages"] or ())
    if "tags" in raw:
        raw["tags"] = tuple(raw["tags"] or ())
    return cls(**raw)  # type: ignore[no-any-return]


@dataclass
class _Shard:
    offset: int = 0
    size: int = 0


@dataclass
class ObservationState:
    store: dict[int, StoreObservation] = field(default_factory=dict[int, StoreObservation])
    reviews: dict[int, ReviewsObservation] = field(default_factory=dict[int, ReviewsObservation])
    tags: dict[int, TagsObservation] = field(default_factory=dict[int, TagsObservation])
    listed: dict[int, ListedApp] = field(default_factory=dict[int, ListedApp])
    review_history: dict[int, list[ReviewsObservation]] = field(
        default_factory=lambda: defaultdict[int, list[ReviewsObservation]](list)
    )
    markers: dict[str, SyncMarker] = field(default_factory=dict[str, SyncMarker])
    last_fetched_at: str | None = None


class ObservationStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.own_file = folder / f"steam-{machine_id()}.jsonl"
        self._lock = threading.RLock()
        self._shards: dict[Path, _Shard] = {}
        self._state = ObservationState()
        self._checked_at = 0.0
        self.version = 0  # bumps whenever new observations were merged

    # --- reading -------------------------------------------------------------------------------

    def _merge(self, obs: Observation) -> None:
        state = self._state
        if isinstance(obs, SyncMarker):
            current_marker = state.markers.get(obs.name)
            if current_marker is None or obs.fetched_at >= current_marker.fetched_at:
                state.markers[obs.name] = obs
            return
        if state.last_fetched_at is None or obs.fetched_at > state.last_fetched_at:
            state.last_fetched_at = obs.fetched_at
        if isinstance(obs, ReviewsObservation):
            state.review_history[obs.appid].append(obs)
            target: dict[int, Any] = state.reviews
        elif isinstance(obs, StoreObservation):
            target = state.store
        elif isinstance(obs, TagsObservation):
            target = state.tags
        else:
            target = state.listed
        current = target.get(obs.appid)
        if current is None or obs.fetched_at >= current.fetched_at:
            target[obs.appid] = obs

    def _read_new(self, path: Path, shard: _Shard) -> int:
        with path.open("rb") as handle:
            handle.seek(shard.offset)
            data = handle.read()
        end = data.rfind(b"\n")
        if end < 0:
            return 0
        merged = 0
        for line in data[: end + 1].splitlines():
            if not line.strip():
                continue
            try:
                obs = _decode(json.loads(line))
            except (ValueError, TypeError, KeyError):
                continue
            if obs is not None:
                self._merge(obs)
                merged += 1
        shard.offset += end + 1
        return merged

    def refresh(self, force: bool = False) -> None:
        with self._lock:
            now = time.monotonic()
            if not force and now - self._checked_at < REFRESH_SECONDS:
                return
            self._checked_at = now
            if not self.folder.is_dir():
                return
            merged = 0
            for path in sorted(self.folder.glob("steam-*.jsonl")):
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                shard = self._shards.setdefault(path, _Shard())
                if size < shard.size:  # file was replaced/truncated: rebuild everything
                    self._shards = {}
                    self._state = ObservationState()
                    self._checked_at = 0.0
                    self.refresh(force=True)
                    return
                if size == shard.size:
                    continue
                try:
                    merged += self._read_new(path, shard)
                except OSError as exc:
                    log.warning(
                        "cannot read observations", extra={"file": str(path), "err": repr(exc)}
                    )
                    continue
                shard.size = size
            if merged:
                self.version += 1

    def state(self) -> ObservationState:
        self.refresh()
        with self._lock:
            return self._state

    def shard_files(self) -> list[Path]:
        return sorted(self.folder.glob("steam-*.jsonl")) if self.folder.is_dir() else []

    # --- writing -------------------------------------------------------------------------------

    def append(self, *observations: Observation) -> None:
        lines = [
            json.dumps({"kind": _KIND_OF[type(obs)], **asdict(obs)}, ensure_ascii=False)
            for obs in observations
        ]
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            with self.own_file.open("a", encoding="utf-8") as handle:
                handle.write("".join(line + "\n" for line in lines))
            # Merge our own writes immediately (and account for them as read).
            shard = self._shards.setdefault(self.own_file, _Shard())
            self._read_new(self.own_file, shard)
            shard.size = self.own_file.stat().st_size
            self.version += 1
