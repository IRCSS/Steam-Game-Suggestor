from __future__ import annotations

import pytest

from app.domain.filters import (
    StudyFilters,
    display_tags,
    filter_games,
    legacy_default_filters,
    matches,
    parse_tags,
    resolve,
)
from app.domain.models import normalize_tags
from tests.helpers import ALL_YEARS, game, open_filters


def test_parse_and_display_tags_match_legacy() -> None:
    assert parse_tags(" Colony Sim , ,ROGUELIKE,") == ("colony sim", "roguelike")
    assert display_tags(" Colony Sim , ,ROGUELIKE,") == ("Colony Sim", "ROGUELIKE")
    assert parse_tags(None) == ()
    assert normalize_tags([" Indie ", "", "  ", "Action"]) == ("Indie", "Action")


def test_empty_fields_fall_back_to_legacy_defaults() -> None:
    b = resolve(StudyFilters(years=ALL_YEARS))
    assert (b.min_revenue, b.min_price, b.min_rank, b.min_percentile) == (0, 0, 1, 0)
    assert b.min_reviews == 20  # legacy fallback is 20, not 0
    assert (b.min_review_score, b.max_review_score, b.max_percentile) == (0, 100, 100)
    assert all(v == float("inf") for v in (b.max_revenue, b.max_price, b.max_rank, b.max_reviews))


def test_non_finite_bound_is_treated_as_empty() -> None:
    b = resolve(open_filters(max_revenue=float("nan"), min_reviews=float("inf")))
    assert b.max_revenue == float("inf")
    assert b.min_reviews == 20


def test_legacy_defaults() -> None:
    d = legacy_default_filters([2022, 2023], 4982)
    assert d.min_revenue == 150_000 and d.max_revenue == 800_000
    assert d.min_price == 0 and d.max_price == 200
    assert d.min_rank == 1 and d.max_rank == 4982
    assert d.min_reviews == 20 and d.max_reviews is None
    assert d.min_review_score == 50 and d.max_review_score == 100
    assert d.years == frozenset({2022, 2023})


@pytest.mark.parametrize(
    ("field", "attr", "value"),
    [
        ("revenue", "estimated_revenue", 225_000),
        ("price", "price", 10.0),
        ("rank", "revenue_rank_in_year", 500),
        ("percentile", "revenue_percentile_in_year", 88.2),
        ("reviews", "total_reviews", 500),
        ("review_score", "review_score", 90.0),
    ],
)
def test_numeric_bounds_are_inclusive(field: str, attr: str, value: float) -> None:
    g = game(**{attr: value})
    assert matches(g, resolve(open_filters(**{f"min_{field}": value})))
    assert matches(g, resolve(open_filters(**{f"max_{field}": value})))
    assert matches(g, resolve(open_filters(**{f"min_{field}": value, f"max_{field}": value})))
    step = 0.01 if isinstance(value, float) else 1
    assert not matches(g, resolve(open_filters(**{f"min_{field}": value + step})))
    assert not matches(g, resolve(open_filters(**{f"max_{field}": value - step})))


def test_min_reviews_fallback_excludes_games_below_20() -> None:
    assert not matches(game(total_reviews=19), resolve(open_filters()))
    assert matches(game(total_reviews=20), resolve(open_filters()))


def test_year_selection() -> None:
    g = game(release_year=2024)
    assert matches(g, resolve(open_filters(years=frozenset({2024}))))
    assert not matches(g, resolve(open_filters(years=frozenset({2022, 2023}))))
    assert not matches(g, resolve(open_filters(years=frozenset())))


def test_required_tags_are_and_combined_with_substring_match() -> None:
    g = game()
    assert matches(g, resolve(open_filters(include_tags="indie, colony sim")))
    assert matches(g, resolve(open_filters(include_tags="ROGUELIKE")))  # substring of tag
    assert matches(g, resolve(open_filters(include_tags="deck")))
    assert not matches(g, resolve(open_filters(include_tags="indie, vr")))


def test_excluded_tags_are_or_combined_with_substring_match() -> None:
    g = game()
    assert not matches(g, resolve(open_filters(exclude_tags="vr, colony")))
    assert not matches(g, resolve(open_filters(exclude_tags="rogue")))
    assert matches(g, resolve(open_filters(exclude_tags="vr, multiplayer")))


def test_tag_matching_uses_trimmed_tags() -> None:
    g = game(tags=normalize_tags([" Puzzle ", "Casual"]))
    assert matches(g, resolve(open_filters(include_tags="puzzle")))
    assert g.tags == ("Puzzle", "Casual")


def test_tag_matching_is_case_insensitive_for_non_ascii() -> None:
    g = game(tags=("Ébauche",))
    assert matches(g, resolve(open_filters(include_tags="ÉBAUCHE")))


def test_filter_games_preserves_order_and_excludes_appids() -> None:
    games = [game(appid=3), game(appid=1), game(appid=2)]
    assert [g.appid for g in filter_games(games, open_filters())] == [3, 1, 2]
    assert [g.appid for g in filter_games(games, open_filters(), {1})] == [3, 2]
