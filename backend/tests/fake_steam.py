"""In-memory fake of the Steam endpoints used by data jobs (httpx.MockTransport handler).

Response shapes mirror real responses captured live on 2026-11-06 (sanitized, trimmed).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import httpx

API_KEY = "TEST-KEY-123"


@dataclass
class FakeApp:
    appid: int
    name: str
    reviews_positive: int
    reviews_negative: int
    price_cents: int | None = 999
    is_free: bool = False
    app_type: str = "game"
    release: str = "Mar 3, 2026"
    coming_soon: bool = False
    languages: str = (
        "English<strong>*</strong>, French<br><strong>*</strong>languages with full audio support"
    )
    tags: dict[str, int] = field(default_factory=lambda: {"Indie": 120, "Roguelike": 90})
    listed: bool = True  # appears in the official app list
    last_modified: int = 1  # unix time of the last change (for if_modified_since)
    positive_texts: list[str] = field(
        default_factory=lambda: ["[b]So addictive[/b], tons of content for the price.", "ok"]
    )
    negative_texts: list[str] = field(
        default_factory=lambda: ["Gets repetitive after 20 hours, endgame is thin."]
    )
    available: bool = True


class FakeSteam:
    def __init__(self, apps: list[FakeApp]) -> None:
        self.apps = {a.appid: a for a in apps}
        self.calls: Counter[str] = Counter()
        self.flaky: dict[str, int] = {}  # endpoint -> number of 429s to return first
        self.seen_key_values: list[str] = []
        self.review_queries: list[dict[str, Any]] = []

    def _maybe_429(self, endpoint: str) -> httpx.Response | None:
        if self.flaky.get(endpoint, 0) > 0:
            self.flaky[endpoint] -= 1
            return httpx.Response(429, headers={"Retry-After": "3"})
        return None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "store.steampowered.com" and url.path == "/api/appdetails":
            self.calls["store"] += 1
            if (r := self._maybe_429("store")) is not None:
                return r
            appid = int(url.params["appids"])
            app = self.apps.get(appid)
            if app is None or not app.available:
                return httpx.Response(200, json={str(appid): {"success": False}})
            data: dict[str, Any] = {
                "type": app.app_type,
                "name": app.name,
                "steam_appid": appid,
                "is_free": app.is_free,
                "short_description": f"{app.name} pitch",
                "supported_languages": app.languages,
                "release_date": {"coming_soon": app.coming_soon, "date": app.release},
            }
            if app.price_cents is not None and not app.is_free:
                data["price_overview"] = {
                    "currency": "USD", "initial": app.price_cents, "final": app.price_cents,
                    "discount_percent": 0, "final_formatted": f"${app.price_cents / 100:.2f}",
                }  # fmt: skip
            return httpx.Response(200, json={str(appid): {"success": True, "data": data}})
        if url.host == "api.steampowered.com" and "IUserReviewsService" in url.path:
            self.calls["reviews"] += 1
            if (r := self._maybe_429("reviews")) is not None:
                return r
            query = json.loads(url.params["input_json"])
            self.review_queries.append(query)
            app = self.apps.get(int(query["appid"]))
            pos, neg = (app.reviews_positive, app.reviews_negative) if app else (0, 0)
            if query.get("review_type") in (1, 2) and app is not None:
                positive = query["review_type"] == 1
                texts = app.positive_texts if positive else app.negative_texts
                reviews = [
                    {"review": t, "voted_up": positive, "votes_up": 10 + i,
                     "author": {"playtime_forever": 600}}
                    for i, t in enumerate(texts)
                ]  # fmt: skip
                return httpx.Response(200, json={"response": {"reviews": reviews}})
            summary = {
                "num_reviews": 1, "review_score": 8, "review_score_desc": "Very Positive",
                "total_positive": pos, "total_negative": neg, "total_reviews": pos + neg,
            }  # fmt: skip
            return httpx.Response(200, json={"response": {"query_summary": summary, "reviews": []}})
        if url.host == "steamspy.com":
            self.calls["steamspy"] += 1
            app = self.apps.get(int(url.params["appid"]))
            tags: object = app.tags if app else []
            return httpx.Response(200, json={"appid": url.params["appid"], "tags": tags})
        if url.host == "api.steampowered.com" and "IStoreService/GetAppList" in url.path:
            self.calls["applist"] += 1
            self.seen_key_values.append(url.params.get("key", ""))
            if url.params.get("key") != API_KEY:
                return httpx.Response(403, text="Forbidden")
            last = int(url.params.get("last_appid", "0"))
            limit = int(url.params.get("max_results", "10000"))
            since = int(url.params.get("if_modified_since", "0"))
            listed = sorted(
                a
                for a, app in self.apps.items()
                if app.listed and a > last and app.last_modified >= since
            )
            page = listed[:limit]
            apps = [
                {"appid": a, "name": self.apps[a].name, "last_modified": self.apps[a].last_modified}
                for a in page
            ]
            body: dict[str, Any] = {"apps": apps}
            if len(listed) > limit:
                body.update(have_more_results=True, last_appid=page[-1])
            return httpx.Response(200, json={"response": body})
        if "steamstatic.com" in url.host:
            return httpx.Response(404)
        return httpx.Response(404)
