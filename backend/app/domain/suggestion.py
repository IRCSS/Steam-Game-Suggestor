"""Uniform random suggestion with session-only repeat avoidance (legacy `suggestGame`)."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.filters import StudyFilters, filter_games
from app.domain.models import LegacyGame


@dataclass(frozen=True, slots=True)
class MatchCount:
    count: int  # matches excluding games already seen this session (when avoiding repeats)
    count_ignoring_history: int
    all_seen: bool  # nothing new left, but suggesting will reset session history


@dataclass(frozen=True, slots=True)
class Suggestion:
    game: LegacyGame | None
    repeat_history_reset: bool
    candidate_count: int


def choose_uniform(candidates: Sequence[LegacyGame], rng: random.Random) -> LegacyGame:
    """Legacy: candidates[Math.floor(Math.random() * candidates.length)] - uniform."""
    return candidates[int(rng.random() * len(candidates))]


def count_matches(
    eligible: Sequence[LegacyGame],
    filters: StudyFilters,
    avoid_repeats: bool,
    seen_appids: frozenset[int],
) -> MatchCount:
    all_matches = filter_games(eligible, filters)
    if avoid_repeats and seen_appids:
        unseen = sum(1 for g in all_matches if g.appid not in seen_appids)
    else:
        unseen = len(all_matches)
    return MatchCount(
        count=unseen,
        count_ignoring_history=len(all_matches),
        all_seen=avoid_repeats and unseen == 0 and len(all_matches) > 0,
    )


def suggest(
    eligible: Sequence[LegacyGame],
    filters: StudyFilters,
    avoid_repeats: bool,
    seen_appids: frozenset[int],
    rng: random.Random,
) -> Suggestion:
    """Pick one matching game uniformly at random.

    When every match was already seen this session, the *session* seen-set is reset (signalled via
    ``repeat_history_reset``) - persistent study statuses are never touched here.
    """
    exclude = seen_appids if avoid_repeats else frozenset[int]()
    candidates = filter_games(eligible, filters, exclude)
    reset = False
    if not candidates and avoid_repeats:
        everything = filter_games(eligible, filters)
        if everything:
            candidates = everything
            reset = True
    if not candidates:
        return Suggestion(game=None, repeat_history_reset=False, candidate_count=0)
    return Suggestion(
        game=choose_uniform(candidates, rng),
        repeat_history_reset=reset,
        candidate_count=len(candidates),
    )
