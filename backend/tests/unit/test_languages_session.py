from __future__ import annotations

from app.domain.languages import (
    LanguageRecord,
    english_flags,
    exclude_non_english,
    parse_supported_languages,
    supports_english,
)
from app.domain.session import HISTORY_LIMIT, SessionStore
from tests.helpers import game

# Real value returned by the Steam store for AppID 1794680 (2026-11-06).
VAMPIRE_LANGUAGES = (
    "English, French, Italian, German, Spanish - Spain, Japanese, Korean, Polish, "
    "Portuguese - Brazil, Russian, Simplified Chinese, Turkish, Ukrainian, Traditional Chinese"
)
# Common store format with full-audio markers and the footnote.
MARKED = (
    "English<strong>*</strong>, French<strong>*</strong>, Simplified Chinese"
    "<br><strong>*</strong>languages with full audio support"
)


def test_parse_plain_and_marked_formats() -> None:
    parsed = parse_supported_languages(VAMPIRE_LANGUAGES)
    assert parsed[0] == "English" and "Spanish - Spain" in parsed and len(parsed) == 14
    assert parse_supported_languages(MARKED) == ("English", "French", "Simplified Chinese")
    assert parse_supported_languages("Portugu&ecirc;s, Korean") == ("Português", "Korean")
    assert parse_supported_languages("") == ()
    assert parse_supported_languages(None) == ()


def test_supports_english() -> None:
    assert supports_english(["Japanese", "English"])
    assert not supports_english(["Japanese", "Simplified Chinese"])
    assert not supports_english([])


def test_record_english_flag() -> None:
    ok = LanguageRecord(1, "ok", ("Japanese",), "t")
    assert ok.english is False
    assert LanguageRecord(2, "ok", ("English",), "t").english is True
    assert LanguageRecord(3, "ok", (), "t").english is None  # no data is not "no English"
    assert LanguageRecord(4, "unavailable", (), "t").english is None


def test_exclude_non_english_keeps_unknown() -> None:
    games = [game(appid=1), game(appid=2), game(appid=3)]
    records = {
        1: LanguageRecord(1, "ok", ("English",), "t"),
        2: LanguageRecord(2, "ok", ("Japanese",), "t"),
    }
    kept = exclude_non_english(games, english_flags(records))
    assert [g.appid for g in kept] == [1, 3]  # 3 has no lookup yet -> kept


def test_session_store_semantics() -> None:
    store = SessionStore()
    for appid in range(1, 15):
        store.record_view("s", appid)
    store.record_view("s", 5)  # re-view moves to front, no duplicate
    history = store.history("s")
    assert len(history) == HISTORY_LIMIT and history[0] == 5 and len(set(history)) == HISTORY_LIMIT
    assert store.seen("s") == frozenset(range(1, 15))  # seen is not limited to 12
    store.reset_repeats("s")
    assert store.seen("s") == frozenset() and store.history("s") == history
    store.clear("s")
    assert store.history("s") == [] and store.seen("other") == frozenset()


def test_session_store_is_bounded() -> None:
    store = SessionStore(max_sessions=3)
    for i in range(5):
        store.record_view(f"s{i}", 1)
    assert store.history("s0") == []  # evicted (re-created empty)
    assert store.history("s4") == [1]
