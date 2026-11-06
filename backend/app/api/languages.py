"""Supported-language coverage (lookups themselves run as data jobs, see api/data.py)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Service
from app.domain.languages import english_flags
from app.schemas.app import LanguageStatusResponse
from app.services import StudyService

router = APIRouter(prefix="/api/languages", tags=["languages"])


def language_status(service: StudyService) -> LanguageStatusResponse:
    catalog = service.catalog()
    records = service.languages.records()
    flags = english_flags(records)
    in_catalog = {appid: flag for appid, flag in flags.items() if appid in catalog.by_appid}
    qualified = set(service.qualified_appids())
    return LanguageStatusResponse(
        total_games=len(catalog.games),
        qualified_games=len(qualified),
        known=len(in_catalog),
        known_qualified=sum(1 for appid in in_catalog if appid in qualified),
        english=sum(1 for flag in in_catalog.values() if flag),
        no_english=sum(1 for flag in in_catalog.values() if not flag),
        unavailable=sum(
            1 for r in records.values() if r.status == "unavailable" and r.appid in catalog.by_appid
        ),
        offline=service.settings.offline,
    )


@router.get("/status")
def get_language_status(service: Service) -> LanguageStatusResponse:
    return language_status(service)
