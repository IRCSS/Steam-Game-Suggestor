"""Direct game lookup (legacy `searchGames` / `findExactGame`). Bypasses all filters."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

from app.domain.models import Game

AUTOCOMPLETE_LIMIT = 12
_DIGITS = re.compile(r"^\d+$")


def _rank_key(game: Game) -> float:
    # Legacy: Number(rank || Infinity)
    return game.revenue_rank_in_year or math.inf


def search_games(
    games: Sequence[Game],
    by_appid: Mapping[int, Game],
    query: str | None,
    limit: int = AUTOCOMPLETE_LIMIT,
) -> list[Game]:
    """Exact numeric AppID wins outright; otherwise case-insensitive name substring matches,
    name-prefix matches first, then best legacy yearly rank. Stable w.r.t. source order."""
    cleaned = str(query or "").strip().lower()
    if not cleaned:
        return []
    if _DIGITS.match(cleaned):
        game = by_appid.get(int(cleaned))
        return [game] if game else []
    matches = [g for g in games if cleaned in g.name.lower()]
    matches.sort(key=lambda g: (not g.name.lower().startswith(cleaned), _rank_key(g)))
    return matches[:limit]


def find_exact_game(
    games: Sequence[Game],
    by_appid: Mapping[int, Game],
    query: str | None,
) -> Game | None:
    """Exact AppID, then exact (trimmed, case-insensitive) name, then best search match."""
    cleaned = str(query or "").strip()
    if not cleaned:
        return None
    if _DIGITS.match(cleaned):
        game = by_appid.get(int(cleaned))
        if game:
            return game
    normalized = cleaned.lower()
    for game in games:
        if game.name.strip().lower() == normalized:
            return game
    results = search_games(games, by_appid, cleaned)
    return results[0] if results else None
