"""Application services: the single place that combines storage with domain logic.

Storage layout (all inside the configurable data folder, safe to share between PCs):
  catalog.sqlite3          read-only game catalog (written only by the importer / build)
  studies/<appid>.json     one file per study (StudyStore)
  cache/languages-*.jsonl  per-PC Steam language lookups (LanguageCache)
Session view history is in memory (SessionStore). Exports go to the export folder.

The ~15.5k compact catalog records are cached in memory; filtering is pure Python domain code so
legacy semantics are reproduced exactly (a few milliseconds per request).
"""

from __future__ import annotations

import random
import re
import sqlite3
import threading
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings
from app.db import queries
from app.db.connection import CatalogError, open_catalog, schema_version
from app.domain.filters import StudyFilters, legacy_default_filters
from app.domain.languages import LanguageRecord, english_flags, exclude_non_english
from app.domain.lookup import find_exact_game, search_games
from app.domain.models import LegacyGame
from app.domain.qualification import CatalogPolicy, qualify
from app.domain.session import SessionStore
from app.domain.suggestion import MatchCount, Suggestion, count_matches, suggest
from app.jobs.language_job import LanguageJob
from app.logging_config import get_logger
from app.providers.steam_store import Artwork, fetch_artwork, make_client
from app.storage.language_cache import LanguageCache
from app.storage.studies import Study, StudyStore

log = get_logger("service")
ARTWORK_CACHE_SIZE = 64
MAX_EXPORT_BYTES = 15_000_000
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class OfflineError(RuntimeError):
    """External requests are disabled (offline mode)."""


@dataclass(frozen=True, slots=True)
class Catalog:
    games: tuple[LegacyGame, ...]
    by_appid: dict[int, LegacyGame]
    tags: tuple[str, ...]
    year_counts: dict[int, int]
    max_rank: int
    import_info: queries.ImportInfo | None

    @classmethod
    def build(cls, games: list[LegacyGame], info: queries.ImportInfo | None) -> Catalog:
        tags = sorted({t for g in games for t in g.tags})  # codepoint order, as legacy HTML
        year_counts = dict(sorted(Counter(g.release_year for g in games).items()))
        max_rank = max((g.qualifying_games_in_year for g in games), default=0)
        return cls(
            games=tuple(games),
            by_appid={g.appid: g for g in games},
            tags=tuple(tags),
            year_counts=year_counts,
            max_rank=max_rank,
            import_info=info,
        )


EMPTY_CATALOG = Catalog.build([], None)


def export_filename(name: str, appid: int) -> str:
    cleaned = _UNSAFE_FILENAME.sub(" ", name).strip(" .") or "game"
    return f"{cleaned[:80].rstrip(' .')} ({appid}).jpg"


class StudyService:
    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection | None = None,
        http_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.settings = settings
        self.catalog_error: str | None = None
        self._conn: sqlite3.Connection | None = conn
        if self._conn is None:
            try:
                self._conn = open_catalog(settings.catalog_path, settings.catalog_immutable)
            except CatalogError as exc:
                self.catalog_error = str(exc)
                log.error("catalog unavailable", extra={"err": str(exc)})
        self._lock = threading.RLock()
        self._catalog: Catalog | None = None
        self._catalog_run_id: int | None = None
        self.sessions = SessionStore()
        self.studies = StudyStore(settings.studies_dir)
        self.languages = LanguageCache(settings.cache_dir)
        self._http_factory = http_factory or make_client
        self.language_job = LanguageJob(
            self.languages, self._http_factory, settings.steam_requests_per_minute
        )
        self._artwork: OrderedDict[int, Artwork | None] = OrderedDict()

    def close(self) -> None:
        self.language_job.cancel()
        self.language_job.join(timeout=5)
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # --- catalog -----------------------------------------------------------------------------

    def catalog(self) -> Catalog:
        with self._lock:
            if self._conn is None:
                return EMPTY_CATALOG
            info = queries.latest_import(self._conn)
            run_id = info.run_id if info else None
            if self._catalog is None or run_id != self._catalog_run_id:
                self._catalog = Catalog.build(queries.load_legacy_games(self._conn), info)
                self._catalog_run_id = run_id
            return self._catalog

    def schema_version(self) -> int:
        with self._lock:
            return schema_version(self._conn) if self._conn is not None else 0

    def policy(self, include_below_threshold: bool) -> CatalogPolicy:
        return CatalogPolicy(
            min_estimated_revenue_usd=self.settings.qualification_min_revenue_usd,
            include_below_threshold=include_below_threshold,
        )

    def default_filters(self) -> StudyFilters:
        catalog = self.catalog()
        return legacy_default_filters(catalog.year_counts.keys(), catalog.max_rank)

    def qualified_count(self) -> int:
        return len(qualify(self.catalog().games, self.policy(False)))

    def qualified_appids(self) -> list[int]:
        return [g.appid for g in qualify(self.catalog().games, self.policy(False))]

    # --- lookup ------------------------------------------------------------------------------

    def get_game(self, appid: int) -> LegacyGame | None:
        return self.catalog().by_appid.get(appid)

    def search(self, query: str, limit: int) -> list[LegacyGame]:
        catalog = self.catalog()
        return search_games(catalog.games, catalog.by_appid, query, limit)

    def resolve(self, query: str) -> LegacyGame | None:
        catalog = self.catalog()
        return find_exact_game(catalog.games, catalog.by_appid, query)

    # --- suggestions -------------------------------------------------------------------------

    def eligible(
        self, include_below_threshold: bool, require_english: bool, exclude_studies: bool
    ) -> list[LegacyGame]:
        games = qualify(self.catalog().games, self.policy(include_below_threshold))
        if require_english:
            games = exclude_non_english(games, english_flags(self.languages.records()))
        if exclude_studies:
            studied = self.studies.appids()
            games = [g for g in games if g.appid not in studied]
        return games

    def count(
        self,
        session_id: str,
        filters: StudyFilters,
        avoid_repeats: bool,
        include_below_threshold: bool,
        require_english: bool = False,
        exclude_studies: bool = True,
    ) -> MatchCount:
        eligible = self.eligible(include_below_threshold, require_english, exclude_studies)
        return count_matches(eligible, filters, avoid_repeats, self.sessions.seen(session_id))

    def suggest(
        self,
        session_id: str,
        filters: StudyFilters,
        avoid_repeats: bool,
        include_below_threshold: bool,
        seed: int | None,
        require_english: bool = False,
        exclude_studies: bool = True,
    ) -> Suggestion:
        eligible = self.eligible(include_below_threshold, require_english, exclude_studies)
        rng = random.Random(seed) if seed is not None else random.SystemRandom()
        result = suggest(eligible, filters, avoid_repeats, self.sessions.seen(session_id), rng)
        if result.repeat_history_reset:
            self.sessions.reset_repeats(session_id)
        if result.game is not None:
            self.sessions.record_view(session_id, result.game.appid)
        return result

    # --- session history ---------------------------------------------------------------------

    def record_manual_view(self, session_id: str, appid: int) -> None:
        self.sessions.record_view(session_id, appid)

    def history(self, session_id: str) -> list[LegacyGame]:
        catalog = self.catalog()
        return [
            catalog.by_appid[a] for a in self.sessions.history(session_id) if a in catalog.by_appid
        ]

    def clear_history(self, session_id: str) -> None:
        self.sessions.clear(session_id)

    # --- studies -----------------------------------------------------------------------------

    def list_studies(self) -> list[Study]:
        return sorted(self.studies.all().values(), key=lambda s: s.added_at, reverse=True)

    def add_study(self, game: LegacyGame) -> Study:
        return self.studies.add(game.appid, game.name)

    def remove_study(self, appid: int) -> bool:
        return self.studies.remove(appid)

    # --- languages ---------------------------------------------------------------------------

    def language_record(self, appid: int) -> LanguageRecord | None:
        return self.languages.records().get(appid)

    def start_language_job(self, scope: str) -> bool:
        if self.settings.offline:
            raise OfflineError("Offline mode is on; Steam requests are disabled.")
        appids = (
            self.qualified_appids()
            if scope == "qualified"
            else [g.appid for g in self.catalog().games]
        )
        return self.language_job.start(appids, scope)

    # --- artwork & exports -------------------------------------------------------------------

    def artwork(self, appid: int) -> Artwork | None:
        """Header artwork fetched on demand from Steam's CDN for the JPEG export (kept only in a
        small in-memory cache, never written to disk)."""
        if self.settings.offline:
            return None
        with self._lock:
            if appid in self._artwork:
                self._artwork.move_to_end(appid)
                return self._artwork[appid]
        with self._http_factory() as client:
            art = fetch_artwork(client, appid)
        with self._lock:
            self._artwork[appid] = art
            while len(self._artwork) > ARTWORK_CACHE_SIZE:
                self._artwork.popitem(last=False)
        return art

    def save_export(self, game: LegacyGame, jpeg: bytes) -> Path:
        if not jpeg.startswith(b"\xff\xd8\xff"):
            raise ValueError("not a JPEG image")
        if len(jpeg) > MAX_EXPORT_BYTES:
            raise ValueError("image too large")
        folder = self.settings.export_dir
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / export_filename(game.name, game.appid)
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(jpeg)
        tmp.replace(target)
        log.info("jpeg exported", extra={"appid": game.appid, "file": str(target)})
        return target
