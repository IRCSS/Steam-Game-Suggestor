"""Data jobs started from the Data tab: refresh existing games, discover new AppIDs, one AppID.

Every job only APPENDS observations (and language records) to this PC's files in the data folder;
nothing in the catalog database is modified, and user state (studies) is never touched.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Literal

from app.domain.languages import LanguageRecord
from app.domain.models import Game
from app.domain.observations import LEGACY_REVIEWS_TO_SALES_MULTIPLIER, StoreObservation
from app.jobs.runner import JobContext
from app.providers.steam_store import (
    fetch_app_list,
    fetch_reviews,
    fetch_store_info,
    language_record_from_store,
)
from app.providers.steamspy import fetch_tags
from app.storage.language_cache import LanguageCache
from app.storage.observations import ObservationState, ObservationStore

# Discovery screening: a game whose reviews x 45 x $70 is below the floor cannot qualify at any
# realistic price, so its store details/tags are not fetched (saves most requests).
MAX_PLAUSIBLE_PRICE_USD = 70.0
APP_LIST_PAGE = 10_000

Part = Literal["reviews", "store", "tags"]
PROVIDER: dict[Part, str] = {"reviews": "reviews", "store": "store", "tags": "steamspy"}


@dataclass(frozen=True, slots=True)
class RefreshParams:
    scope: Literal["qualified", "all", "studies"] = "qualified"
    years: tuple[int, ...] = ()  # empty = all years
    min_revenue_usd: int | None = None  # None = catalog floor; applies to scope "qualified"
    parts: tuple[Part, ...] = ("reviews", "store")
    stale_days: int = 7  # skip parts fetched more recently than this (0 = always refetch)
    only_missing_languages: bool = False
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class DiscoverParams:
    max_new: int = 500  # how many newly listed AppIDs to screen in this run
    fetch_tags: bool = True
    min_revenue_usd: int | None = None


@dataclass(frozen=True, slots=True)
class Target:
    appid: int
    parts: tuple[Part, ...]


@dataclass
class Preview:
    items: int
    requests: int
    seconds: float
    needs_key: bool = False
    notes: list[str] = field(default_factory=list[str])


def _fresh(fetched_at: str | None, stale_days: int, now: datetime) -> bool:
    if fetched_at is None or stale_days <= 0:
        return False
    try:
        when = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    return now - when < timedelta(days=stale_days)


def select_refresh_targets(
    games: Sequence[Game],
    params: RefreshParams,
    floor_usd: int,
    study_appids: frozenset[int],
    languages: dict[int, LanguageRecord],
    observations: ObservationState,
    now: datetime | None = None,
) -> list[Target]:
    now = now or datetime.now(UTC)
    minimum = floor_usd if params.min_revenue_usd is None else params.min_revenue_usd
    targets: list[Target] = []
    for game in games:
        if params.years and game.release_year not in params.years:
            continue
        if params.scope == "studies" and game.appid not in study_appids:
            continue
        if params.scope == "qualified" and game.estimated_revenue < minimum:
            continue
        if params.only_missing_languages and game.appid in languages:
            continue
        last = {
            "reviews": observations.reviews.get(game.appid),
            "store": observations.store.get(game.appid),
            "tags": observations.tags.get(game.appid),
        }
        parts: tuple[Part, ...] = tuple(
            part
            for part in params.parts
            if not _fresh(getattr(last[part], "fetched_at", None), params.stale_days, now)
        )
        if parts:
            targets.append(Target(game.appid, parts))
        if params.limit and len(targets) >= params.limit:
            break
    return targets


def estimate(items: Iterable[Iterable[str]], intervals: dict[str, float]) -> tuple[int, float]:
    """Requests and seconds for items calling the given providers once each (sequential worker;
    each provider waits for its own interval, so an item takes ~ the slowest provider's)."""
    requests = 0
    seconds = 0.0
    for providers in items:
        used = list(providers)
        requests += len(used)
        seconds += max((intervals.get(p, 1.0) for p in used), default=0.0) + 0.25
    return requests, seconds


def save_store(
    store: StoreObservation, observations: ObservationStore, languages: LanguageCache
) -> None:
    observations.append(store)
    if (store.status == "ok" and store.languages) or store.status != "ok":
        languages.append(language_record_from_store(store))


def make_refresh_task(
    targets: Sequence[Target], observations: ObservationStore, languages: LanguageCache
) -> Callable[[JobContext], str]:
    def task(ctx: JobContext) -> str:
        ctx.set_total(len(targets))
        for target in targets:
            if ctx.cancelled:
                break
            appid = target.appid
            if "reviews" in target.parts:
                reviews = ctx.call(
                    "reviews", f"AppID {appid} reviews", partial(fetch_reviews, appid=appid)
                )
                if reviews is not None:
                    observations.append(reviews)
                    ctx.count("reviews_updated")
            if "store" in target.parts:
                store = ctx.call(
                    "store", f"AppID {appid} store", partial(fetch_store_info, appid=appid)
                )
                if store is not None:
                    save_store(store, observations, languages)
                    ctx.count("store_updated" if store.status == "ok" else "unavailable")
            if "tags" in target.parts:
                tags = ctx.call("steamspy", f"AppID {appid} tags", partial(fetch_tags, appid=appid))
                if tags is not None:
                    observations.append(tags)
                    ctx.count("tags_updated")
            ctx.advance()
        return f"Refreshed {ctx.status.done} games ({ctx.status.requests} requests)."

    return task


def make_discover_task(
    params: DiscoverParams,
    api_key: str,
    floor_usd: int,
    known_appids: frozenset[int],
    observations: ObservationStore,
    languages: LanguageCache,
) -> Callable[[JobContext], str]:
    minimum = floor_usd if params.min_revenue_usd is None else params.min_revenue_usd

    def task(ctx: JobContext) -> str:
        state = observations.state()
        cursor = max([*known_appids, *state.listed.keys()], default=0)
        ctx.log(f"Listing games with AppID above {cursor}")
        listed_now = 0
        while not ctx.cancelled:
            page = ctx.call(
                "applist",
                "app list",
                partial(
                    fetch_app_list, api_key=api_key, last_appid=cursor, max_results=APP_LIST_PAGE
                ),
            )
            if page is None:
                ctx.log("App list unavailable - check the Steam Web API key in Settings.")
                return "Could not read Steam's app list."
            new = [app for app in page.apps if app.appid > cursor]
            if new:
                observations.append(*new)
                listed_now += len(new)
            ctx.count("listed", len(new))
            if not page.have_more or page.last_appid <= cursor:
                break
            cursor = page.last_appid
        state = observations.state()
        pending = sorted(
            appid
            for appid in state.listed
            if appid not in state.reviews and appid not in known_appids
        )[: params.max_new]
        ctx.log(f"{listed_now} newly listed; screening {len(pending)}")
        ctx.set_total(len(pending))
        for appid in pending:
            if ctx.cancelled:
                break
            reviews = ctx.call(
                "reviews", f"AppID {appid} reviews", partial(fetch_reviews, appid=appid)
            )
            ctx.advance()
            if reviews is None:
                continue
            observations.append(reviews)
            ctx.count("screened")
            ceiling = (
                reviews.total_reviews * LEGACY_REVIEWS_TO_SALES_MULTIPLIER * MAX_PLAUSIBLE_PRICE_USD
            )
            if ceiling < minimum:
                ctx.count("below_floor")
                continue
            store = ctx.call(
                "store", f"AppID {appid} store", partial(fetch_store_info, appid=appid)
            )
            if store is None:
                continue
            save_store(store, observations, languages)
            if store.status != "ok" or store.coming_soon:
                ctx.count("not_released_or_not_game")
                continue
            price = 0.0 if store.is_free else (store.price_cents or 0) / 100
            revenue = reviews.total_reviews * LEGACY_REVIEWS_TO_SALES_MULTIPLIER * price
            if revenue < minimum:
                ctx.count("below_floor")
                continue
            ctx.count("added_qualified")
            ctx.log(f"New qualified game: {store.name} ({appid}) ~${revenue:,.0f}")
            if params.fetch_tags:
                tags = ctx.call("steamspy", f"AppID {appid} tags", partial(fetch_tags, appid=appid))
                if tags is not None:
                    observations.append(tags)
        added = ctx.status.counters.get("added_qualified", 0)
        return (
            f"Listed {listed_now} new AppIDs, screened {ctx.status.done},"
            f" added {added} qualified games."
        )

    return task


def make_single_app_task(
    appid: int, observations: ObservationStore, languages: LanguageCache
) -> Callable[[JobContext], str]:
    task = make_refresh_task([Target(appid, ("reviews", "store", "tags"))], observations, languages)

    def single(ctx: JobContext) -> str:
        task(ctx)
        return f"AppID {appid} updated ({ctx.status.requests} requests)."

    return single
