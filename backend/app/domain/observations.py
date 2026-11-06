"""Steam observations and how they overlay the legacy catalog. Pure functions, no I/O.

An observation is one fetch result with a timestamp. The newest observation of each kind wins.
Untouched legacy games stay byte-identical to the import (and their recomputed ranks equal the
legacy ranks); refreshed games are flagged ``data_source="steam"``; games found by discovery that
were never in the legacy file are ``data_source="steam_new"``.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from app.domain.models import Game
from app.domain.ranks import compute_ranks
from app.domain.revenue import LEGACY_REVIEWS_TO_SALES_MULTIPLIER

MAX_TAGS = 20
NEW_GAME_SOURCE_OFFSET = 1_000_000_000  # new games sort after all legacy rows on rank ties
_YEAR = re.compile(r"\b(19[89]\d|20\d\d)\b")

StoreStatus = Literal["ok", "unavailable", "not_game"]


@dataclass(frozen=True, slots=True)
class StoreObservation:
    appid: int
    fetched_at: str
    status: StoreStatus
    app_type: str = ""
    name: str = ""
    short_description: str = ""
    is_free: bool | None = None
    price_cents: int | None = None  # undiscounted ("initial") price; None = no price shown
    currency: str | None = None
    release_date_text: str = ""
    release_year: int | None = None
    coming_soon: bool = False
    languages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewsObservation:
    appid: int
    fetched_at: str
    total_reviews: int
    total_positive: int
    total_negative: int

    @property
    def review_score(self) -> float:
        return (
            round(100 * self.total_positive / self.total_reviews, 2) if self.total_reviews else 0.0
        )


@dataclass(frozen=True, slots=True)
class TagsObservation:
    appid: int
    fetched_at: str
    tags: tuple[str, ...]
    source: str = "steamspy"


@dataclass(frozen=True, slots=True)
class ListedApp:
    """An AppID seen in Steam's official app list (discovery), not necessarily screened yet."""

    appid: int
    fetched_at: str
    name: str = ""
    last_modified: int | None = None


def parse_release_year(text: str) -> int | None:
    match = _YEAR.search(text or "")
    return int(match.group(1)) if match else None


def estimate_revenue(total_reviews: int, price: float) -> int:
    """Same versioned model as the legacy data: total reviews x 45 x price."""
    return round(total_reviews * LEGACY_REVIEWS_TO_SALES_MULTIPLIER * price)


def _store_price(store: StoreObservation) -> float | None:
    if store.is_free:
        return 0.0
    if store.price_cents is not None and (store.currency or "USD") == "USD":
        return store.price_cents / 100
    return None


def _overlay(
    game: Game,
    store: StoreObservation | None,
    reviews: ReviewsObservation | None,
    tags: TagsObservation | None,
) -> Game:
    changes: dict[str, object] = {}
    price = game.price
    total_reviews = game.total_reviews
    if reviews is not None:
        total_reviews = reviews.total_reviews
        changes.update(
            total_reviews=reviews.total_reviews,
            review_score=reviews.review_score,
            reviews_observed_at=reviews.fetched_at,
        )
    if store is not None and store.status == "ok":
        changes.update(store_observed_at=store.fetched_at, is_free=store.is_free)
        if store.name:
            changes["name"] = store.name
        if store.short_description:
            changes["short_description"] = store.short_description
        if store.release_date_text:
            changes["release_date"] = store.release_date_text
        if store.release_year:
            changes["release_year"] = store.release_year
        store_price = _store_price(store)
        if store_price is not None:
            price = store_price
            changes.update(price=price, price_context="steam_store_initial_price_usd")
    if tags is not None and tags.tags:
        changes.update(
            tags=tags.tags[:MAX_TAGS], tags_lower=(), tags_observed_at=tags.fetched_at,
            tags_source=tags.source,
        )  # fmt: skip
    if not changes:
        return game
    changes["estimated_revenue"] = estimate_revenue(total_reviews, price)
    changes["data_source"] = "steam" if game.data_source == "legacy_import" else game.data_source
    return dataclasses.replace(game, **changes)  # type: ignore[arg-type]


def _new_game(
    store: StoreObservation, reviews: ReviewsObservation, tags: TagsObservation | None
) -> Game | None:
    if store.status != "ok" or store.coming_soon or store.release_year is None:
        return None
    price = _store_price(store)
    if price is None:
        return None  # paid game without a USD price: revenue cannot be estimated
    base = Game(
        appid=store.appid,
        name=store.name or f"App {store.appid}",
        short_description=store.short_description,
        tags=(),
        release_year=store.release_year,
        price=price,
        total_reviews=reviews.total_reviews,
        review_score=reviews.review_score,
        estimated_revenue=estimate_revenue(reviews.total_reviews, price),
        revenue_rank_in_year=0,
        qualifying_games_in_year=0,
        revenue_percentile_in_year=0.0,
        source_index=NEW_GAME_SOURCE_OFFSET + store.appid,
        data_source="steam_new",
        reviews_observed_at=reviews.fetched_at,
        store_observed_at=store.fetched_at,
        tags_source="none",
        price_context="steam_store_initial_price_usd",
        release_date=store.release_date_text or None,
        is_free=store.is_free,
    )
    return _overlay(base, None, None, tags)


def build_catalog(
    legacy: Iterable[Game],
    store: Mapping[int, StoreObservation],
    reviews: Mapping[int, ReviewsObservation],
    tags: Mapping[int, TagsObservation],
) -> list[Game]:
    """Legacy games overlaid with the newest observations, plus newly discovered games, ranked."""
    games: list[Game] = []
    seen: set[int] = set()
    for game in legacy:
        seen.add(game.appid)
        games.append(
            _overlay(game, store.get(game.appid), reviews.get(game.appid), tags.get(game.appid))
        )
    for appid, observation in store.items():
        if appid in seen or appid not in reviews:
            continue
        if observation.app_type and observation.app_type != "game":
            continue
        new = _new_game(observation, reviews[appid], tags.get(appid))
        if new is not None:
            games.append(new)
    games.sort(key=lambda g: g.source_index)
    return compute_ranks(games)
