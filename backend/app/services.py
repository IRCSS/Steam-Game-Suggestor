"""Application services: the single place that combines repository data with domain logic.

The full legacy catalog (~15.5k compact records) is cached in memory and reloaded automatically
when a new import run is detected. Filtering stays in Python domain code so legacy semantics are
reproduced exactly; at this size it runs in a few milliseconds.
"""

from __future__ import annotations

import random
import sqlite3
import threading
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.db import queries
from app.db.connection import open_database, schema_version
from app.domain.filters import StudyFilters, legacy_default_filters
from app.domain.lookup import find_exact_game, search_games
from app.domain.models import LegacyGame
from app.domain.qualification import CatalogPolicy, qualify
from app.domain.suggestion import MatchCount, Suggestion, count_matches, suggest


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


class StudyService:
    def __init__(self, settings: Settings, conn: sqlite3.Connection | None = None) -> None:
        self.settings = settings
        self._conn = conn or open_database(settings.db_path)
        self._lock = threading.RLock()
        self._catalog: Catalog | None = None
        self._catalog_run_id: int | None = None

    @classmethod
    def for_path(cls, settings: Settings, db_path: Path) -> StudyService:
        return cls(settings, open_database(db_path))

    @contextmanager
    def db(self) -> Generator[sqlite3.Connection]:
        with self._lock:
            yield self._conn

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- catalog -----------------------------------------------------------------------------

    def catalog(self) -> Catalog:
        with self.db() as conn:
            info = queries.latest_import(conn)
            run_id = info.run_id if info else None
            if self._catalog is None or run_id != self._catalog_run_id:
                self._catalog = Catalog.build(queries.load_legacy_games(conn), info)
                self._catalog_run_id = run_id
            return self._catalog

    def schema_version(self) -> int:
        with self.db() as conn:
            return schema_version(conn)

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

    def is_qualified(self, game: LegacyGame) -> bool:
        return game.estimated_revenue >= self.settings.qualification_min_revenue_usd

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

    def count(
        self,
        session_id: str,
        filters: StudyFilters,
        avoid_repeats: bool,
        include_below_threshold: bool,
    ) -> MatchCount:
        eligible = qualify(self.catalog().games, self.policy(include_below_threshold))
        with self.db() as conn:
            seen = queries.seen_appids(conn, session_id)
        return count_matches(eligible, filters, avoid_repeats, seen)

    def suggest(
        self,
        session_id: str,
        filters: StudyFilters,
        avoid_repeats: bool,
        include_below_threshold: bool,
        seed: int | None,
    ) -> Suggestion:
        eligible = qualify(self.catalog().games, self.policy(include_below_threshold))
        rng = random.Random(seed) if seed is not None else random.SystemRandom()
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                seen = queries.seen_appids(conn, session_id)
                result = suggest(eligible, filters, avoid_repeats, seen, rng)
                if result.repeat_history_reset:
                    queries.reset_repeat_history(conn, session_id)
                if result.game is not None:
                    queries.record_view(conn, session_id, result.game.appid, "suggested")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return result

    # --- session history ---------------------------------------------------------------------

    def record_manual_view(self, session_id: str, appid: int) -> None:
        with self.db() as conn:
            queries.record_view(conn, session_id, appid, "manual_lookup")

    def history(self, session_id: str) -> list[LegacyGame]:
        catalog = self.catalog()
        with self.db() as conn:
            appids = queries.history_appids(conn, session_id)
        return [catalog.by_appid[a] for a in appids if a in catalog.by_appid]

    def clear_history(self, session_id: str) -> None:
        with self.db() as conn:
            queries.clear_history(conn, session_id)
