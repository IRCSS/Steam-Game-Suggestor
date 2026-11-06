"""Most helpful Steam reviews (text) - the input for "why it worked / what held it back".

Verified live 2026-11-06: IUserReviewsService/GetAppReviews selects positive/negative reviews with
the numeric ``review_type`` 1 / 2 (string values are silently ignored), and "most helpful" only
looks at the last 30 days unless ``day_range`` is raised (capped at 365). Review text is only used
transiently for one research run and never stored.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from app.providers.steam_store import REVIEWS_URL, as_dict, as_list, get_json, to_int

_BBCODE = re.compile(r"\[/?[a-z0-9*]+(?:=[^\]]*)?\]", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
MAX_REVIEW_CHARS = 900


@dataclass(frozen=True, slots=True)
class ReviewSample:
    voted_up: bool
    votes_up: int
    playtime_hours: int
    text: str


def clean_review(text: str, limit: int = MAX_REVIEW_CHARS) -> str:
    cleaned = _SPACE.sub(" ", _BBCODE.sub(" ", text)).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def fetch_review_samples(
    client: httpx.Client, appid: int, side: Literal["positive", "negative"], count: int = 40
) -> list[ReviewSample]:
    query = {
        "appid": appid,
        "languages": ["english"],
        "review_type": 1 if side == "positive" else 2,
        "num_per_page": max(1, min(100, count)),
        # "Most helpful" defaults to the last 30 days only (6 of 40 for a 2023 game in a live
        # check); Steam caps day_range at 365, which returns the full sample.
        "filter": "all",
        "day_range": 3650,
    }
    payload = get_json(client, REVIEWS_URL, {"input_json": json.dumps(query)}, f"{side} reviews")
    samples: list[ReviewSample] = []
    for raw in as_list(as_dict(payload.get("response")).get("reviews")):
        review = as_dict(raw)
        text = clean_review(str(review.get("review") or ""))
        if len(text) < 20:
            continue  # "10/10", emoji-only, etc. carry no reasons
        author = as_dict(review.get("author"))
        samples.append(
            ReviewSample(
                voted_up=bool(review.get("voted_up")),
                votes_up=to_int(review.get("votes_up")),
                playtime_hours=to_int(author.get("playtime_forever")) // 60,
                text=text,
            )
        )
    return samples
