"""Supported-language parsing and the "Must support English" filter. Pure functions, no I/O.

Steam's store `supported_languages` field is a small HTML string, e.g.
  "English<strong>*</strong>, French, Spanish - Spain<br><strong>*</strong>languages with full
   audio support"
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from app.domain.models import Game

LanguageStatus = Literal["ok", "unavailable"]
_TAG = re.compile(r"<[^>]+>")
_FOOTNOTE = re.compile(r"<br\s*/?>", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LanguageRecord:
    """Cached result of one store lookup for an AppID."""

    appid: int
    status: LanguageStatus  # unavailable = store returned no data (delisted, region-locked, ...)
    languages: tuple[str, ...]
    fetched_at: str
    source: str = "steam_store_appdetails"

    @property
    def english(self) -> bool | None:
        """True/False when known; None when the store gave no language data."""
        if self.status != "ok" or not self.languages:
            return None
        return supports_english(self.languages)


def parse_supported_languages(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    head = _FOOTNOTE.split(raw, maxsplit=1)[0]
    text = html.unescape(_TAG.sub("", head))
    languages: list[str] = []
    for part in text.split(","):
        name = part.strip().rstrip("*").strip()
        if name and "full audio support" not in name.lower() and name not in languages:
            languages.append(name)
    return tuple(languages)


def supports_english(languages: Iterable[str]) -> bool:
    return any(
        lang.casefold() == "english" or lang.casefold().startswith("english ") for lang in languages
    )


def english_flags(records: Mapping[int, LanguageRecord]) -> dict[int, bool]:
    """AppID -> True/False for every game whose English support is known."""
    flags: dict[int, bool] = {}
    for appid, record in records.items():
        english = record.english
        if english is not None:
            flags[appid] = english
    return flags


def exclude_non_english(games: Iterable[Game], flags: Mapping[int, bool]) -> list[Game]:
    """Drop games KNOWN to have no English support. Unknown games are kept (and labelled in the
    UI) - a missing lookup is not evidence of missing English."""
    return [g for g in games if flags.get(g.appid, True)]
