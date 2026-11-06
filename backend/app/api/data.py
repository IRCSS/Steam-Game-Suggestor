"""Data tab: status of the local dataset and user-started, bounded update jobs."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException

from app.api.deps import Service
from app.jobs.runner import JobStatus
from app.jobs.sync import DeepCheckParams, DiscoverParams, Preview, RefreshParams
from app.providers.steam_store import StoreError, fetch_app_list
from app.schemas.app import (
    DataStatus,
    DeepCheckOptions,
    DiscoverOptions,
    JobPreview,
    JobRequest,
    JobView,
    KeyTestResult,
    RefreshOptions,
    ShardInfo,
)
from app.services import OfflineError, StudyService

router = APIRouter(prefix="/api/data", tags=["data"])


def job_view(status: JobStatus) -> JobView:
    return JobView(
        job_id=status.job_id,
        kind=status.kind,
        label=status.label,
        state=status.state,
        total=status.total,
        done=status.done,
        counters=dict(status.counters),
        requests=status.requests,
        started_at=status.started_at,
        finished_at=status.finished_at,
        eta_seconds=status.eta_seconds(),
        message=status.message,
        recent=list(status.recent),
    )


def _refresh_params(options: RefreshOptions | None, languages_only: bool = False) -> RefreshParams:
    options = options or RefreshOptions()
    if languages_only:
        # Languages come with the store details request; only games without them yet.
        return RefreshParams(
            scope=options.scope,
            years=tuple(options.years),
            min_revenue_usd=options.min_revenue_usd,
            parts=("store",),
            stale_days=0,
            only_missing_languages=True,
            limit=options.limit,
        )
    return RefreshParams(
        scope=options.scope,
        years=tuple(options.years),
        min_revenue_usd=options.min_revenue_usd,
        parts=tuple(dict.fromkeys(options.parts)),
        stale_days=options.stale_days,
        limit=options.limit,
    )


def _discover_params(options: DiscoverOptions | None) -> DiscoverParams:
    o = options or DiscoverOptions()
    return DiscoverParams(
        max_new=o.max_new,
        fetch_tags=o.fetch_tags,
        min_revenue_usd=o.min_revenue_usd,
        recheck_unreleased=o.recheck_unreleased,
        max_recheck=o.max_recheck,
    )


def _deep_params(options: DeepCheckOptions | None) -> DeepCheckParams:
    o = options or DeepCheckOptions()
    return DeepCheckParams(
        changed_since_days=o.changed_since_days,
        recheck_set_aside=o.recheck_set_aside,
        min_age_days=o.min_age_days,
        max_apps=o.max_apps,
        fetch_tags=o.fetch_tags,
    )


def _preview(service: StudyService, body: JobRequest) -> Preview:
    if body.kind == "discover":
        return service.preview_discover(_discover_params(body.discover))
    if body.kind == "deep_check":
        return service.preview_deep_check(_deep_params(body.deep_check))
    if body.kind == "app":
        return Preview(items=1, requests=3, seconds=5)
    return service.preview_refresh(_refresh_params(body.refresh, body.kind == "languages"))


@router.get("/status")
def data_status(service: Service) -> DataStatus:
    catalog = service.catalog()
    sources = Counter(g.data_source for g in catalog.games)
    state = service.observations.state()
    set_aside = service.set_aside_counts()
    return DataStatus(
        data_dir=str(service.settings.data_dir),
        total_games=len(catalog.games),
        qualified_games=service.qualified_count(),
        legacy_unchanged=sources.get("legacy_import", 0),
        refreshed=sources.get("steam", 0),
        discovered=sources.get("steam_new", 0),
        years={str(k): v for k, v in catalog.year_counts.items()},
        last_update=state.last_fetched_at,
        discovery_cursor_appid=service.discovery_cursor(),
        listed_not_screened=service.pending_screening(),
        set_aside_unreleased=set_aside["unreleased"],
        set_aside_below_floor=set_aside["below_floor"],
        last_deep_check=service.last_deep_check(),
        languages_known=len(service.languages.records()),
        steam_api_key_set=bool(service.api_key()),
        offline=service.settings.offline,
        qualification_threshold_usd=service.settings.qualification_min_revenue_usd,
        observation_files=[
            ShardInfo(file=p.name, bytes=p.stat().st_size)
            for p in service.observations.shard_files()
        ],
        seconds_per_request=service.jobs.intervals,
        job=job_view(service.jobs.status),
    )


@router.post("/jobs/preview")
def preview_job(service: Service, body: JobRequest) -> JobPreview:
    preview = _preview(service, body)
    return JobPreview(
        items=preview.items,
        requests=preview.requests,
        seconds=preview.seconds,
        needs_key=preview.needs_key,
        notes=preview.notes,
    )


@router.post("/jobs")
def start_job(service: Service, body: JobRequest) -> JobView:
    try:
        if body.kind == "discover":
            started = service.start_discover(_discover_params(body.discover))
        elif body.kind == "deep_check":
            started = service.start_deep_check(_deep_params(body.deep_check))
        elif body.kind == "app":
            if body.appid is None:
                raise HTTPException(422, "appid is required")
            started = service.start_single_app(body.appid)
        else:
            label = body.label or (
                "Look up languages" if body.kind == "languages" else "Refresh existing games"
            )
            started = service.start_refresh(
                _refresh_params(body.refresh, body.kind == "languages"), label
            )
    except OfflineError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not started:
        raise HTTPException(409, "Another data job is already running.")
    return job_view(service.jobs.status)


@router.get("/jobs/current")
def current_job(service: Service) -> JobView:
    return job_view(service.jobs.status)


@router.post("/jobs/cancel")
def cancel_job(service: Service) -> JobView:
    service.jobs.cancel()
    return job_view(service.jobs.status)


@router.post("/test-key")
def test_key(service: Service) -> KeyTestResult:
    """One request to Steam's app list to check the configured Web API key."""
    if service.settings.offline:
        return KeyTestResult(ok=False, message="Offline mode is on.")
    key = service.api_key()
    if not key:
        return KeyTestResult(ok=False, message="No Steam Web API key set (Settings).")
    try:
        with service.http_client() as client:
            page = fetch_app_list(client, key, service.discovery_cursor(), 1)
    except StoreError as exc:
        return KeyTestResult(ok=False, message=str(exc))
    newest = f" Next new AppID: {page.apps[0].appid}." if page.apps else " No newer AppIDs."
    return KeyTestResult(ok=True, message=f"Key works.{newest}")
