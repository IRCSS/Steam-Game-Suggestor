"""Steam adapters. All HTTP goes through an injected ``httpx.Client`` (tests: MockTransport).

Verified live on 2026-11-06:
* Store appdetails (keyless) ``filters=basic,price_overview,release_date`` -> name, type,
  description, is_free, undiscounted USD price, release date, supported languages (~5 KB). A store
  web endpoint, not a Steamworks contract: kept replaceable; failures mean "unknown".
* IUserReviewsService/GetAppReviews (keyless) with ``languages: ["all"]`` -> all-language review
  totals (positive + negative), consistent with the legacy dataset's review counts. WITHOUT that
  parameter Steam silently returns English-only totals (~half).
* IStoreService/GetAppList REQUIRES a Steam Web API key (keyless calls return 403); the older
  ISteamApps/GetAppList is gone (404). The key is never included in errors or logs.
* CDN artwork for the JPEG export.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.db.connection import utc_now
from app.domain.languages import LanguageRecord, parse_supported_languages
from app.domain.observations import (
    ListedApp,
    ReviewsObservation,
    StoreObservation,
    parse_release_year,
)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
REVIEWS_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
APPLIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
USER_AGENT = "SteamStudyTool/0.3 (local research tool)"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class StoreError(Exception):
    def __init__(self, message: str, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        transport=transport,
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _as_dict(value: object) -> dict[str, object]:
    """Untrusted JSON: treat anything that is not an object as empty."""
    if isinstance(value, dict):
        items: dict[object, object] = value  # pyright: ignore[reportUnknownVariableType]
        return {str(k): v for k, v in items.items()}
    return {}


# Public names for other provider modules (untrusted-JSON helpers).
def as_dict(value: object) -> dict[str, object]:
    return _as_dict(value)


def as_list(value: object) -> list[object]:
    return _as_list(value)


def to_int(value: object, default: int = 0) -> int:
    return _int(value, default)


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        items: list[object] = value  # pyright: ignore[reportUnknownVariableType]
        return items
    return []


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[call-overload, no-any-return]
    except (TypeError, ValueError):
        return default


def get_json(
    client: httpx.Client, url: str, params: dict[str, str | int], what: str
) -> dict[str, object]:
    """GET + JSON with uniform, secret-free error handling (no URLs/params in messages)."""
    try:
        response = client.get(url, params=params)
    except httpx.TransportError as exc:
        raise StoreError(
            f"{what}: network error ({exc.__class__.__name__})", retryable=True
        ) from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise StoreError(
            f"{what}: HTTP {response.status_code}",
            retryable=True,
            retry_after=_retry_after(response),
        )
    if response.status_code in (401, 403):
        raise StoreError(f"{what}: access denied (HTTP {response.status_code})", retryable=False)
    if response.status_code != 200:
        raise StoreError(f"{what}: HTTP {response.status_code}", retryable=False)
    try:
        return _as_dict(response.json())
    except ValueError as exc:
        raise StoreError(f"{what}: invalid JSON", retryable=True) from exc


# --- store details -----------------------------------------------------------------------------


def fetch_store_info(client: httpx.Client, appid: int) -> StoreObservation:
    payload = get_json(
        client,
        APPDETAILS_URL,
        {
            "appids": appid,
            "filters": "basic,price_overview,release_date",
            "cc": "us",
            "l": "english",
        },
        "store details",
    )
    now = utc_now()
    entry = _as_dict(payload.get(str(appid)))
    if not entry.get("success"):
        return StoreObservation(appid=appid, fetched_at=now, status="unavailable")
    data = _as_dict(entry.get("data"))
    app_type = str(data.get("type") or "")
    price = _as_dict(data.get("price_overview"))
    release = _as_dict(data.get("release_date"))
    release_text = str(release.get("date") or "")
    languages_raw = data.get("supported_languages")
    return StoreObservation(
        appid=appid,
        fetched_at=now,
        status="ok" if app_type in ("game", "") else "not_game",
        app_type=app_type,
        name=str(data.get("name") or ""),
        short_description=str(data.get("short_description") or ""),
        is_free=bool(data["is_free"]) if "is_free" in data else None,
        price_cents=_price_cents(price),
        currency=str(price.get("currency")) if price.get("currency") else None,
        release_date_text=release_text,
        release_year=parse_release_year(release_text),
        coming_soon=bool(release.get("coming_soon")),
        languages=parse_supported_languages(
            languages_raw if isinstance(languages_raw, str) else None
        ),
        header_image=steam_image_url(data.get("header_image")),
    )


def _price_cents(price: dict[str, object]) -> int | None:
    cents = _int(price.get("initial"), -1) if price else -1
    return cents if cents >= 0 else None


def language_record_from_store(store: StoreObservation) -> LanguageRecord:
    return LanguageRecord(
        appid=store.appid,
        status="ok" if store.status == "ok" else "unavailable",
        languages=store.languages,
        fetched_at=store.fetched_at,
    )


def fetch_languages(client: httpx.Client, appid: int) -> LanguageRecord:
    return language_record_from_store(fetch_store_info(client, appid))


# --- reviews -------------------------------------------------------------------------------------


def fetch_reviews(client: httpx.Client, appid: int) -> ReviewsObservation:
    query = {
        "appid": appid,
        "languages": ["all"],  # all-language totals, like the legacy dataset
        "review_type": "all",
        "purchase_type": "all",
        "num_per_page": 1,
    }
    payload = get_json(client, REVIEWS_URL, {"input_json": json.dumps(query)}, "reviews")
    summary = _as_dict(_as_dict(payload.get("response")).get("query_summary"))
    if not summary:
        raise StoreError("reviews: no summary returned", retryable=False)
    positive = _int(summary.get("total_positive"))
    negative = _int(summary.get("total_negative"))
    return ReviewsObservation(
        appid=appid,
        fetched_at=utc_now(),
        total_reviews=_int(summary.get("total_reviews"), positive + negative),
        total_positive=positive,
        total_negative=negative,
    )


# --- app list (discovery) ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppListPage:
    apps: list[ListedApp]
    have_more: bool
    last_appid: int


def fetch_app_list(
    client: httpx.Client,
    api_key: str,
    last_appid: int,
    max_results: int = 10_000,
    if_modified_since: int | None = None,
) -> AppListPage:
    """One page of Steam's official game list, ordered by AppID. With ``if_modified_since``
    (unix time) only apps changed since then are returned - including OLD AppIDs, which is how
    games released long after their store page was created are found."""
    if not api_key:
        raise StoreError("app list: a Steam Web API key is required (Settings)", retryable=False)
    params: dict[str, str | int] = {
        "key": api_key,
        "include_games": "true",
        "include_dlc": "false",
        "include_software": "false",
        "include_videos": "false",
        "include_hardware": "false",
        "last_appid": last_appid,
        "max_results": max_results,
    }
    if if_modified_since is not None:
        params["if_modified_since"] = if_modified_since
    payload = get_json(client, APPLIST_URL, params, "app list")
    response = _as_dict(payload.get("response"))
    now = utc_now()
    apps = [
        ListedApp(
            appid=_int(app.get("appid")),
            fetched_at=now,
            name=str(app.get("name") or ""),
            last_modified=_int(app.get("last_modified"), 0) or None,
        )
        for app in (_as_dict(a) for a in _as_list(response.get("apps")))
        if _int(app.get("appid")) > 0
    ]
    return AppListPage(
        apps=apps,
        have_more=bool(response.get("have_more_results")),
        last_appid=_int(response.get("last_appid"), apps[-1].appid if apps else last_appid),
    )


# --- artwork -------------------------------------------------------------------------------------


def steam_image_url(value: object) -> str:
    """An artwork URL from Steam's store data, kept only if it points at Steam's image CDN (the
    URL is shown in the browser and fetched by the export proxy). "" otherwise."""
    if not isinstance(value, str) or len(value) > 500:
        return ""
    url = urlsplit(value)
    host = (url.hostname or "").lower()
    return value if url.scheme == "https" and host.endswith(".steamstatic.com") else ""


def artwork_urls(appid: int, header_image: str | None = None) -> list[str]:
    """Steam's recorded header URL first (newer apps only have hashed paths), then the classic
    AppID-based paths that work for most older apps."""
    preferred = [header_image] if header_image and steam_image_url(header_image) else []
    return [
        *preferred,
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_616x353.jpg",
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
    ]


@dataclass(frozen=True, slots=True)
class Artwork:
    content: bytes
    content_type: str


def fetch_artwork(
    client: httpx.Client, appid: int, header_image: str | None = None, max_bytes: int = 5_000_000
) -> Artwork | None:
    for url in artwork_urls(appid, header_image):
        try:
            response = client.get(url)
        except httpx.TransportError:
            continue
        content_type = response.headers.get("Content-Type", "")
        if (
            response.status_code == 200
            and content_type.startswith("image/")
            and len(response.content) <= max_bytes
        ):
            return Artwork(response.content, content_type.split(";")[0])
    return None
