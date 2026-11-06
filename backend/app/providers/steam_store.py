"""Steam store adapters (public, unauthenticated endpoints).

* appdetails (``filters=basic``) -> supported languages. This is a store web endpoint, not a
  documented Steamworks Web API contract: keep it replaceable and treat failures as "unknown".
* CDN artwork -> bytes for the JPEG export (proxied so the UI can embed it same-origin).

All HTTP goes through an injected ``httpx.Client`` so tests use ``httpx.MockTransport``.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.db.connection import utc_now
from app.domain.languages import LanguageRecord, parse_supported_languages

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
USER_AGENT = "SteamStudyTool/0.2 (local research tool)"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


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


def fetch_languages(client: httpx.Client, appid: int) -> LanguageRecord:
    try:
        response = client.get(
            APPDETAILS_URL, params={"appids": appid, "filters": "basic", "l": "english", "cc": "us"}
        )
    except httpx.TransportError as exc:
        raise StoreError(f"network error: {exc.__class__.__name__}", retryable=True) from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise StoreError(
            f"HTTP {response.status_code}", retryable=True, retry_after=_retry_after(response)
        )
    if response.status_code != 200:
        raise StoreError(f"HTTP {response.status_code}", retryable=False)
    try:
        payload: object = response.json()
    except ValueError as exc:
        raise StoreError("invalid JSON", retryable=True) from exc
    now = utc_now()
    entry = _as_dict(_as_dict(payload).get(str(appid)))
    if not entry.get("success"):
        return LanguageRecord(appid=appid, status="unavailable", languages=(), fetched_at=now)
    raw = _as_dict(entry.get("data")).get("supported_languages")
    languages = parse_supported_languages(raw if isinstance(raw, str) else None)
    return LanguageRecord(appid=appid, status="ok", languages=languages, fetched_at=now)


def _as_dict(value: object) -> dict[str, object]:
    """Untrusted JSON: treat anything that is not an object as empty."""
    if isinstance(value, dict):
        items: dict[object, object] = value  # pyright: ignore[reportUnknownVariableType]
        return {str(k): v for k, v in items.items()}
    return {}


def artwork_urls(appid: int) -> list[str]:
    return [
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_616x353.jpg",
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
    ]


@dataclass(frozen=True, slots=True)
class Artwork:
    content: bytes
    content_type: str


def fetch_artwork(client: httpx.Client, appid: int, max_bytes: int = 5_000_000) -> Artwork | None:
    for url in artwork_urls(appid):
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
