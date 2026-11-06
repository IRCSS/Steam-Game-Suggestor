from __future__ import annotations

import random
from collections import Counter

from app.domain.lookup import find_exact_game, search_games
from app.domain.qualification import CatalogPolicy, qualify
from app.domain.revenue import legacy_estimate_usd
from app.domain.suggestion import choose_uniform, count_matches, suggest
from tests.helpers import game, open_filters

GAMES = [game(appid=i, estimated_revenue=100_000 + i) for i in range(1, 11)]


def test_seeded_choice_is_reproducible() -> None:
    a = [choose_uniform(GAMES, random.Random(42)).appid for _ in range(5)]
    b = [choose_uniform(GAMES, random.Random(42)).appid for _ in range(5)]
    assert a == b


def test_choice_is_uniform_over_candidates() -> None:
    rng = random.Random(7)
    counts = Counter(choose_uniform(GAMES, rng).appid for _ in range(20_000))
    assert set(counts) == {g.appid for g in GAMES}
    expected = 20_000 / len(GAMES)
    # chi-square with 9 dof: 99.9th percentile ~ 27.9
    chi2 = sum((c - expected) ** 2 / expected for c in counts.values())
    assert chi2 < 27.9


def test_avoid_repeats_until_exhausted_then_reset() -> None:
    rng = random.Random(1)
    seen: set[int] = set()
    for _ in range(len(GAMES)):
        result = suggest(GAMES, open_filters(), True, frozenset(seen), rng)
        assert result.game is not None
        assert result.game.appid not in seen
        assert not result.repeat_history_reset
        seen.add(result.game.appid)
    result = suggest(GAMES, open_filters(), True, frozenset(seen), rng)
    assert result.game is not None and result.repeat_history_reset
    assert result.candidate_count == len(GAMES)


def test_repeats_allowed_when_avoid_disabled() -> None:
    seen = frozenset(g.appid for g in GAMES)
    result = suggest(GAMES, open_filters(), False, seen, random.Random(3))
    assert result.game is not None and not result.repeat_history_reset


def test_no_matches() -> None:
    result = suggest(
        GAMES, open_filters(include_tags="nonexistent"), True, frozenset(), random.Random()
    )
    assert result.game is None and result.candidate_count == 0


def test_count_matches_reports_all_seen() -> None:
    seen = frozenset(g.appid for g in GAMES)
    c = count_matches(GAMES, open_filters(), True, seen)
    assert (c.count, c.count_ignoring_history, c.all_seen) == (0, 10, True)
    c = count_matches(GAMES, open_filters(), False, seen)
    assert (c.count, c.all_seen) == (10, False)
    c = count_matches(GAMES, open_filters(include_tags="zzz"), True, frozenset())
    assert (c.count, c.all_seen) == (0, False)


def test_qualification_floor_inclusive_and_exploration_mode() -> None:
    games = [game(appid=1, estimated_revenue=99_999), game(appid=2, estimated_revenue=100_000)]
    assert [g.appid for g in qualify(games, CatalogPolicy())] == [2]
    assert len(qualify(games, CatalogPolicy(include_below_threshold=True))) == 2
    assert [g.appid for g in qualify(games, CatalogPolicy(min_estimated_revenue_usd=0))] == [1, 2]


def test_legacy_revenue_formula() -> None:
    assert legacy_estimate_usd(250_334, 3.74) == 42_131_212  # Vampire Survivors in legacy data
    assert legacy_estimate_usd(100, 0.0) == 0


LOOKUP = [
    game(appid=10, name="Super Hero", revenue_rank_in_year=50),
    game(appid=11, name="The Hero Saga", revenue_rank_in_year=1),
    game(appid=12, name="Hero Quest", revenue_rank_in_year=900),
    game(appid=13, name="hero", revenue_rank_in_year=2000),
    game(appid=14, name="Heroine", revenue_rank_in_year=10),
]
BY_APPID = {g.appid: g for g in LOOKUP}


def test_search_prefers_prefix_then_rank() -> None:
    names = [g.name for g in search_games(LOOKUP, BY_APPID, "  HERO ")]
    assert names == ["Heroine", "Hero Quest", "hero", "The Hero Saga", "Super Hero"]


def test_search_numeric_is_exact_appid_only() -> None:
    assert [g.appid for g in search_games(LOOKUP, BY_APPID, "12")] == [12]
    assert search_games(LOOKUP, BY_APPID, "1") == []  # no partial AppID matches
    assert search_games(LOOKUP, BY_APPID, "   ") == []


def test_search_limit() -> None:
    many = [game(appid=i, name=f"Game {i}") for i in range(30)]
    assert len(search_games(many, {g.appid: g for g in many}, "game")) == 12


def test_find_exact_game_priority() -> None:
    assert find_exact_game(LOOKUP, BY_APPID, "13").appid == 13  # type: ignore[union-attr]
    assert find_exact_game(LOOKUP, BY_APPID, "HERO").appid == 13  # type: ignore[union-attr]
    assert find_exact_game(LOOKUP, BY_APPID, "her").appid == 14  # type: ignore[union-attr]
    assert find_exact_game(LOOKUP, BY_APPID, "nothing") is None
    assert find_exact_game(LOOKUP, BY_APPID, "") is None
