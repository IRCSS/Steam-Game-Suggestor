"""Data jobs started from the Data tab: refresh existing games, add new games (since the last
AppID, plus a capped re-check of recently listed unreleased games), the occasional deep check,
and single AppIDs.

Every job only APPENDS observations (and language records) to this PC's files in the data folder;
nothing in the catalog database is modified, and user state (studies) is never touched.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Literal

from app.db.connection import utc_now
from app.domain.languages import LanguageRecord
from app.domain.models import Game
from app.domain.observations import (
    LEGACY_REVIEWS_TO_SALES_MULTIPLIER,
    ListedApp,
    StoreObservation,
    SyncMarker,
)
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


SetAsideReason = Literal["unreleased", "below_floor"]
DEEP_CHECK_MARKER = "deep_check_completed"


@dataclass(frozen=True, slots=True)
class SetAside:
    """A screened AppID that is not in the catalog (yet): it had no reviews / was not released,
    or its reviews could not reach the floor. These are what re-checks look at."""

    appid: int
    reason: SetAsideReason
    checked_at: str  # last time anything was fetched for it
    first_seen_at: str  # when discovery first listed / screened it


def set_aside_apps(state: ObservationState, catalog_appids: frozenset[int]) -> list[SetAside]:
    out: list[SetAside] = []
    for appid, reviews in state.reviews.items():
        if appid in catalog_appids:
            continue  # in the catalog: "Update existing games" keeps it fresh
        store = state.store.get(appid)
        if store is not None and store.status == "not_game":
            continue  # soundtracks, tools, demos...: never a study candidate
        unreleased = reviews.total_reviews == 0 or (
            store is not None and (store.coming_soon or store.status == "unavailable")
        )
        checked = max(reviews.fetched_at, store.fetched_at if store else "")
        history = state.review_history.get(appid) or [reviews]
        listed = state.listed.get(appid)
        first = min(history[0].fetched_at, listed.fetched_at if listed else history[0].fetched_at)
        out.append(SetAside(appid, "unreleased" if unreleased else "below_floor", checked, first))
    return out


def _older_than(timestamp: str, days: float, now: datetime) -> bool:
    try:
        return now - datetime.fromisoformat(timestamp) >= timedelta(days=days)
    except ValueError:
        return True


def recheck_candidates(
    state: ObservationState,
    catalog_appids: frozenset[int],
    *,
    reasons: tuple[SetAsideReason, ...],
    checked_before_days: float,
    first_seen_within_days: float | None,
    limit: int | None,
    now: datetime | None = None,
) -> list[int]:
    """Set-aside AppIDs due for another look, least recently checked first."""
    now = now or datetime.now(UTC)
    due = [
        item
        for item in set_aside_apps(state, catalog_appids)
        if item.reason in reasons
        and _older_than(item.checked_at, checked_before_days, now)
        and (
            first_seen_within_days is None
            or not _older_than(item.first_seen_at, first_seen_within_days, now)
        )
    ]
    due.sort(key=lambda item: item.checked_at)
    appids = [item.appid for item in due]
    return appids[:limit] if limit is not None else appids


@dataclass(frozen=True, slots=True)
class DiscoverParams:
    max_new: int = 500  # how many newly listed AppIDs to screen in this run
    fetch_tags: bool = True
    min_revenue_usd: int | None = None
    # Cheap catch-up for pre-release store pages: re-check recently listed games that had no
    # reviews / were not released yet when last screened.
    recheck_unreleased: bool = True
    max_recheck: int = 200
    recheck_after_days: int = 14
    recheck_window_days: int = 365


@dataclass(frozen=True, slots=True)
class DeepCheckParams:
    """The slow, occasional sweep for edge cases (several hours for a year's worth)."""

    changed_since_days: int = 365  # scan Steam's list for games changed in this period
    recheck_set_aside: bool = True  # re-check every set-aside game ...
    min_age_days: int = 30  # ... last checked at least this long ago
    max_apps: int | None = None
    fetch_tags: bool = True
    min_revenue_usd: int | None = None


def screen_app(
    ctx: JobContext,
    appid: int,
    minimum: float,
    fetch_tags_too: bool,
    observations: ObservationStore,
    languages: LanguageCache,
) -> None:
    """One screening pass: reviews first (1 request); store info and tags only if the game could
    reach the floor. Counts the outcome on the job."""
    reviews = ctx.call("reviews", f"AppID {appid} reviews", partial(fetch_reviews, appid=appid))
    if reviews is None:
        return
    observations.append(reviews)
    ctx.count("screened")
    ceiling = reviews.total_reviews * LEGACY_REVIEWS_TO_SALES_MULTIPLIER * MAX_PLAUSIBLE_PRICE_USD
    if ceiling < minimum:
        ctx.count("unreleased_or_no_reviews" if reviews.total_reviews == 0 else "below_floor")
        return
    store = ctx.call("store", f"AppID {appid} store", partial(fetch_store_info, appid=appid))
    if store is None:
        return
    save_store(store, observations, languages)
    if store.status != "ok" or store.coming_soon:
        ctx.count("not_released_or_not_game")
        return
    price = 0.0 if store.is_free else (store.price_cents or 0) / 100
    revenue = reviews.total_reviews * LEGACY_REVIEWS_TO_SALES_MULTIPLIER * price
    if revenue < minimum:
        ctx.count("below_floor")
        return
    ctx.count("added_qualified")
    ctx.log(f"Qualified game: {store.name} ({appid}) ~${revenue:,.0f}")
    if fetch_tags_too:
        tags = ctx.call("steamspy", f"AppID {appid} tags", partial(fetch_tags, appid=appid))
        if tags is not None:
            observations.append(tags)


def _list_apps(
    ctx: JobContext,
    api_key: str,
    observations: ObservationStore,
    start_after: int,
    if_modified_since: int | None = None,
) -> list[ListedApp] | None:
    """Page through Steam's app list (from ``start_after``), saving newly seen AppIDs."""
    known = observations.state().listed
    cursor = start_after
    found: list[ListedApp] = []
    while not ctx.cancelled:
        page = ctx.call(
            "applist",
            "app list",
            partial(
                fetch_app_list,
                api_key=api_key,
                last_appid=cursor,
                max_results=APP_LIST_PAGE,
                if_modified_since=if_modified_since,
            ),
        )
        if page is None:
            ctx.log("App list unavailable - check the Steam Web API key in Settings.")
            return None
        apps = [app for app in page.apps if app.appid > cursor]
        found.extend(apps)
        unseen = [app for app in apps if app.appid not in known]
        if unseen:
            observations.append(*unseen)
        ctx.count("listed", len(apps))
        if not page.have_more or page.last_appid <= cursor:
            break
        cursor = page.last_appid
    return found


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
        if _list_apps(ctx, api_key, observations, cursor) is None:
            return "Could not read Steam's app list."
        listed_now = ctx.status.counters.get("listed", 0)
        state = observations.state()
        pending = sorted(
            appid
            for appid in state.listed
            if appid not in state.reviews and appid not in known_appids
        )[: params.max_new]
        rechecks: list[int] = []
        if params.recheck_unreleased and params.max_recheck > 0:
            rechecks = recheck_candidates(
                state,
                known_appids,
                reasons=("unreleased",),
                checked_before_days=params.recheck_after_days,
                first_seen_within_days=params.recheck_window_days,
                limit=params.max_recheck,
            )
        ctx.log(
            f"{listed_now} newly listed; screening {len(pending)} new"
            f" + re-checking {len(rechecks)} not yet released"
        )
        ctx.set_total(len(pending) + len(rechecks))
        for appid in [*pending, *rechecks]:
            if ctx.cancelled:
                break
            screen_app(ctx, appid, minimum, params.fetch_tags, observations, languages)
            ctx.advance()
        added = ctx.status.counters.get("added_qualified", 0)
        return (
            f"Listed {listed_now} new AppIDs, screened {len(pending)} new and re-checked"
            f" {len(rechecks)} unreleased; added {added} qualified games."
        )

    return task


def make_deep_check_task(
    params: DeepCheckParams,
    api_key: str,
    floor_usd: int,
    known_appids: frozenset[int],
    observations: ObservationStore,
    languages: LanguageCache,
) -> Callable[[JobContext], str]:
    """Edge-case sweep: (1) games CHANGED on Steam in the period - catches old AppIDs released
    late and pages that were not public before; (2) every set-aside game not checked recently."""
    minimum = floor_usd if params.min_revenue_usd is None else params.min_revenue_usd

    def task(ctx: JobContext) -> str:
        started = utc_now()
        since = datetime.now(UTC) - timedelta(days=params.changed_since_days)
        ctx.log(f"Listing games changed on Steam since {since.date().isoformat()}")
        changed = _list_apps(
            ctx, api_key, observations, 0, if_modified_since=int(since.timestamp())
        )
        if changed is None:
            return "Could not read Steam's app list."
        state = observations.state()
        set_aside = {item.appid: item for item in set_aside_apps(state, known_appids)}
        targets: dict[int, None] = {}
        for app in changed:
            if app.appid in known_appids:
                continue  # in the catalog: refreshed by "Update existing games"
            store = state.store.get(app.appid)
            if store is not None and store.status == "not_game":
                continue
            previous = set_aside.get(app.appid)
            changed_after_check = previous is None or (
                app.last_modified is not None
                and datetime.fromtimestamp(app.last_modified, UTC).isoformat() > previous.checked_at
            )
            if app.appid not in state.reviews or changed_after_check:
                targets[app.appid] = None
        from_scan = len(targets)
        if params.recheck_set_aside:
            for appid in recheck_candidates(
                state,
                known_appids,
                reasons=("unreleased", "below_floor"),
                checked_before_days=params.min_age_days,
                first_seen_within_days=None,
                limit=None,
            ):
                targets.setdefault(appid, None)
        work = list(targets)[: params.max_apps] if params.max_apps else list(targets)
        ctx.log(
            f"{from_scan} changed games to check + {len(targets) - from_scan} set-aside games"
            f" to re-check ({len(work)} this run)"
        )
        ctx.set_total(len(work))
        for appid in work:
            if ctx.cancelled:
                break
            screen_app(ctx, appid, minimum, params.fetch_tags, observations, languages)
            ctx.advance()
        if not ctx.cancelled and len(work) == len(targets):
            observations.append(SyncMarker(DEEP_CHECK_MARKER, started, f"{len(work)} checked"))
        added = ctx.status.counters.get("added_qualified", 0)
        return f"Deep check: looked at {ctx.status.done} games, added {added} qualified games."

    return task


def make_single_app_task(
    appid: int, observations: ObservationStore, languages: LanguageCache
) -> Callable[[JobContext], str]:
    task = make_refresh_task([Target(appid, ("reviews", "store", "tags"))], observations, languages)

    def single(ctx: JobContext) -> str:
        task(ctx)
        return f"AppID {appid} updated ({ctx.status.requests} requests)."

    return single
