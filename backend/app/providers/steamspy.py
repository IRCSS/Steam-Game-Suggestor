"""SteamSpy (third-party, keyless, ~1 request/second): community tags with vote counts.

Used only for tags (Steam's store API exposes genres/categories, not user tags). The legacy
dataset's tags are the same kind of user tags. Verified live on 2026-11-06.
"""

from __future__ import annotations

import httpx

from app.db.connection import utc_now
from app.domain.observations import MAX_TAGS, TagsObservation
from app.providers.steam_store import get_json

STEAMSPY_URL = "https://steamspy.com/api.php"


def fetch_tags(client: httpx.Client, appid: int) -> TagsObservation:
    payload = get_json(client, STEAMSPY_URL, {"request": "appdetails", "appid": appid}, "tags")
    raw = payload.get("tags")
    votes: dict[str, int] = {}
    if isinstance(raw, dict):  # SteamSpy returns [] instead of {} when there are no tags
        items: dict[object, object] = raw  # pyright: ignore[reportUnknownVariableType]
        for tag, count in items.items():
            try:
                votes[str(tag).strip()] = int(count)  # type: ignore[call-overload]
            except (TypeError, ValueError):
                continue
    ordered = sorted(votes, key=lambda t: (-votes[t], t))
    return TagsObservation(
        appid=appid, fetched_at=utc_now(), tags=tuple(t for t in ordered if t)[:MAX_TAGS]
    )
