"""Supported-language lookups from the Steam store (user-started background job)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import Service
from app.domain.languages import english_flags
from app.schemas.app import LanguageFetchRequest, LanguageJobView, LanguageStatusResponse
from app.services import OfflineError, StudyService

router = APIRouter(prefix="/api/languages", tags=["languages"])


def _status(service: StudyService) -> LanguageStatusResponse:
    catalog = service.catalog()
    records = service.languages.records()
    flags = english_flags(records)
    in_catalog = {appid: flag for appid, flag in flags.items() if appid in catalog.by_appid}
    qualified = set(service.qualified_appids())
    job = service.language_job.status
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
        job=LanguageJobView(
            state=job.state,
            scope=job.scope,
            total=job.total,
            done=job.done,
            found=job.found,
            unavailable=job.unavailable,
            errors=job.errors,
            skipped=job.skipped,
            started_at=job.started_at,
            finished_at=job.finished_at,
            message=job.message,
            recent=list(job.recent),
            seconds_per_request=service.language_job.interval,
        ),
    )


@router.get("/status")
def language_status(service: Service) -> LanguageStatusResponse:
    return _status(service)


@router.post("/fetch")
def start_fetch(service: Service, body: LanguageFetchRequest) -> LanguageStatusResponse:
    try:
        started = service.start_language_job(body.scope)
    except OfflineError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not started:
        raise HTTPException(409, "A language lookup is already running.")
    return _status(service)


@router.post("/cancel")
def cancel_fetch(service: Service) -> LanguageStatusResponse:
    service.language_job.cancel()
    return _status(service)
