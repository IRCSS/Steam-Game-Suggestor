"""Application services: the single place that combines storage with domain logic.

Storage layout (all inside the configurable data folder, safe to share between PCs):
  catalog.sqlite3          read-only game catalog (written only by the importer / build)
  studies/<appid>.json     one file per study (StudyStore)
  cache/languages-*.jsonl  per-PC Steam language lookups (LanguageCache)
  observations/steam-*.jsonl  per-PC Steam refresh/discovery results, overlaid on the catalog
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

from app.config import Settings, read_settings_file
from app.db import queries
from app.db.connection import CatalogError, open_catalog, schema_version
from app.domain.filters import StudyFilters, legacy_default_filters
from app.domain.languages import LanguageRecord, english_flags, exclude_non_english
from app.domain.lookup import find_exact_game, search_games
from app.domain.models import Game
from app.domain.observations import build_catalog
from app.domain.qualification import CatalogPolicy, qualify
from app.domain.session import SessionStore
from app.domain.suggestion import MatchCount, Suggestion, count_matches, suggest
from app.jobs.runner import JobRunner
from app.jobs.sync import (
    DEEP_CHECK_MARKER,
    DeepCheckParams,
    DiscoverParams,
    Preview,
    RefreshParams,
    Target,
    estimate,
    make_deep_check_task,
    make_discover_task,
    make_refresh_task,
    make_single_app_task,
    recheck_candidates,
    select_refresh_targets,
    set_aside_apps,
)
from app.logging_config import get_logger
from app.providers.steam_store import Artwork, fetch_artwork, make_client
from app.storage.language_cache import LanguageCache
from app.storage.observations import ObservationStore
from app.storage.studies import Study, StudyStore

log = get_logger("service")
ARTWORK_CACHE_SIZE = 64
MAX_EXPORT_BYTES = 15_000_000
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class OfflineError(RuntimeError):
    """External requests are disabled (offline mode)."""


@dataclass(frozen=True, slots=True)
class Catalog:
    games: tuple[Game, ...]
    by_appid: dict[int, Game]
    tags: tuple[str, ...]
    year_counts: dict[int, int]
    max_rank: int
    import_info: queries.ImportInfo | None

    @classmethod
    def build(cls, games: list[Game], info: queries.ImportInfo | None) -> Catalog:
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
        self._catalog_key: tuple[int | None, int] | None = None
        self._legacy: list[Game] = []
        self._legacy_run_id: int | None = -1
        self.sessions = SessionStore()
        self.studies = StudyStore(settings.studies_dir)
        self.languages = LanguageCache(settings.cache_dir)
        self._http_factory = http_factory or make_client
        self.observations = ObservationStore(settings.data_dir / "observations")
        self.jobs = JobRunner(
            self._http_factory,
            {
                "store": 60.0 / settings.steam_requests_per_minute,
                "reviews": 60.0 / settings.steam_requests_per_minute,
                "steamspy": 1.2,  # SteamSpy allows ~1 request/second
                "applist": 1.0,
            },
        )
        self._artwork: OrderedDict[int, Artwork | None] = OrderedDict()

    def close(self) -> None:
        self.jobs.cancel()
        self.jobs.join(timeout=5)
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # --- catalog -----------------------------------------------------------------------------

    def catalog(self) -> Catalog:
        """Legacy catalog overlaid with Steam observations from every PC, ranked; cached until
        a new import or new observations arrive."""
        with self._lock:
            if self._conn is None:
                return EMPTY_CATALOG
            info = queries.latest_import(self._conn)
            run_id = info.run_id if info else None
            if run_id != self._legacy_run_id:
                self._legacy = queries.load_legacy_games(self._conn)
                self._legacy_run_id = run_id
            state = self.observations.state()
            key = (run_id, self.observations.version)
            if self._catalog is None or key != self._catalog_key:
                games = build_catalog(self._legacy, state.store, state.reviews, state.tags)
                self._catalog = Catalog.build(games, info)
                self._catalog_key = key
            return self._catalog

    def legacy_games(self) -> list[Game]:
        self.catalog()
        return self._legacy

    def http_client(self) -> httpx.Client:
        return self._http_factory()

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

    def get_game(self, appid: int) -> Game | None:
        return self.catalog().by_appid.get(appid)

    def search(self, query: str, limit: int) -> list[Game]:
        catalog = self.catalog()
        return search_games(catalog.games, catalog.by_appid, query, limit)

    def resolve(self, query: str) -> Game | None:
        catalog = self.catalog()
        return find_exact_game(catalog.games, catalog.by_appid, query)

    # --- suggestions -------------------------------------------------------------------------

    def eligible(
        self, include_below_threshold: bool, require_english: bool, exclude_studies: bool
    ) -> list[Game]:
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

    def history(self, session_id: str) -> list[Game]:
        catalog = self.catalog()
        return [
            catalog.by_appid[a] for a in self.sessions.history(session_id) if a in catalog.by_appid
        ]

    def clear_history(self, session_id: str) -> None:
        self.sessions.clear(session_id)

    # --- studies -----------------------------------------------------------------------------

    def list_studies(self) -> list[Study]:
        return sorted(self.studies.all().values(), key=lambda s: s.added_at, reverse=True)

    def add_study(self, game: Game) -> Study:
        return self.studies.add(game.appid, game.name)

    def remove_study(self, appid: int) -> bool:
        return self.studies.remove(appid)

    # --- languages ---------------------------------------------------------------------------

    def language_record(self, appid: int) -> LanguageRecord | None:
        return self.languages.records().get(appid)

    # --- data jobs ---------------------------------------------------------------------------

    def _require_online(self) -> None:
        if self.settings.offline:
            raise OfflineError("Offline mode is on; Steam requests are disabled (Settings).")

    def refresh_targets(self, params: RefreshParams) -> list[Target]:
        return select_refresh_targets(
            self.catalog().games,
            params,
            self.settings.qualification_min_revenue_usd,
            self.studies.appids(),
            self.languages.records(),
            self.observations.state(),
        )

    def preview_refresh(self, params: RefreshParams) -> Preview:
        targets = self.refresh_targets(params)
        providers = {"reviews": "reviews", "store": "store", "tags": "steamspy"}
        requests, seconds = estimate(
            ([providers[p] for p in t.parts] for t in targets), self.jobs.intervals
        )
        return Preview(items=len(targets), requests=requests, seconds=seconds)

    def start_refresh(self, params: RefreshParams, label: str) -> bool:
        self._require_online()
        targets = self.refresh_targets(params)
        return self.jobs.start(
            "refresh", label, make_refresh_task(targets, self.observations, self.languages)
        )

    def known_appids(self) -> frozenset[int]:
        return frozenset(g.appid for g in self._legacy) | frozenset(self.catalog().by_appid)

    def discovery_cursor(self) -> int:
        state = self.observations.state()
        return max([*self.known_appids(), *state.listed.keys()], default=0)

    def pending_screening(self) -> int:
        state = self.observations.state()
        known = self.known_appids()
        return sum(1 for a in state.listed if a not in state.reviews and a not in known)

    def discover_rechecks(self, params: DiscoverParams) -> list[int]:
        if not params.recheck_unreleased or params.max_recheck <= 0:
            return []
        return recheck_candidates(
            self.observations.state(),
            self.known_appids(),
            reasons=("unreleased",),
            checked_before_days=params.recheck_after_days,
            first_seen_within_days=params.recheck_window_days,
            limit=params.max_recheck,
        )

    def preview_discover(self, params: DiscoverParams) -> Preview:
        # The number of new AppIDs is only known after reading Steam's list: assume max_new.
        new_items = max(min(self.pending_screening(), params.max_new), params.max_new)
        rechecks = len(self.discover_rechecks(params))
        items = new_items + rechecks
        requests, seconds = estimate((["reviews"] for _ in range(items)), self.jobs.intervals)
        notes = [
            f"Up to {params.max_new:,} new AppIDs"
            + (
                f" + {rechecks:,} recently listed games that were not released yet"
                if rechecks
                else ""
            )
            + ". Most have too few reviews to reach the floor and cost one request each; only "
            "promising ones are looked up further, so the real time is usually lower."
        ]
        return Preview(
            items=items,
            requests=requests + 1,
            seconds=seconds,
            needs_key=not self.api_key(),
            notes=notes,
        )

    def deep_check_rechecks(self, params: DeepCheckParams) -> list[int]:
        if not params.recheck_set_aside:
            return []
        return recheck_candidates(
            self.observations.state(),
            self.known_appids(),
            reasons=("unreleased", "below_floor"),
            checked_before_days=params.min_age_days,
            first_seen_within_days=None,
            limit=None,
        )

    def preview_deep_check(self, params: DeepCheckParams) -> Preview:
        rechecks = len(self.deep_check_rechecks(params))
        items = min(rechecks, params.max_apps) if params.max_apps else rechecks
        requests, seconds = estimate((["reviews"] for _ in range(items)), self.jobs.intervals)
        # Changed-game scan: a year of Steam typically has tens of thousands of changed games;
        # most are already known or excluded, but the size is only known after listing.
        notes = [
            f"Known now: {rechecks:,} set-aside games to re-check. The scan for games changed in "
            f"the last {params.changed_since_days} days adds more, known only once Steam's list "
            "is read - this is the slow part and can take several hours. It can be stopped and "
            "started again; already-checked games are skipped next time."
        ]
        return Preview(
            items=items, requests=requests + 1, seconds=seconds, needs_key=not self.api_key(),
            notes=notes,
        )  # fmt: skip

    def last_deep_check(self) -> str | None:
        marker = self.observations.state().markers.get(DEEP_CHECK_MARKER)
        return marker.fetched_at if marker else None

    def set_aside_counts(self) -> dict[str, int]:
        counts = {"unreleased": 0, "below_floor": 0}
        for item in set_aside_apps(self.observations.state(), self.known_appids()):
            counts[item.reason] += 1
        return counts

    def api_key(self) -> str:
        """Steam Web API key from settings.json (server side only; never returned by the API)."""
        content, _ = read_settings_file(self.settings.app_dir)
        return content.steam.api_key

    def start_discover(self, params: DiscoverParams) -> bool:
        self._require_online()
        key = self.api_key()
        if not key:
            raise OfflineError("Add a Steam Web API key in Settings to discover new games.")
        task = make_discover_task(
            params,
            key,
            self.settings.qualification_min_revenue_usd,
            self.known_appids(),
            self.observations,
            self.languages,
        )
        return self.jobs.start("discover", "Add new games", task)

    def start_deep_check(self, params: DeepCheckParams) -> bool:
        self._require_online()
        key = self.api_key()
        if not key:
            raise OfflineError("Add a Steam Web API key in Settings to run the deep check.")
        task = make_deep_check_task(
            params,
            key,
            self.settings.qualification_min_revenue_usd,
            self.known_appids(),
            self.observations,
            self.languages,
        )
        return self.jobs.start("deep_check", "Deep check", task)

    def start_single_app(self, appid: int) -> bool:
        self._require_online()
        task = make_single_app_task(appid, self.observations, self.languages)
        return self.jobs.start("app", f"Update AppID {appid}", task)

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

    def save_export(self, game: Game, jpeg: bytes) -> Path:
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
