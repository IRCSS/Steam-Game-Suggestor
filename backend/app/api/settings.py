"""Global settings (gear icon). Persisted in settings.json next to the app."""

from __future__ import annotations

import os
import shutil
from typing import cast

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import Service
from app.config import (
    SettingsFile,
    read_settings_file,
    settings_from_file,
    settings_path,
    write_settings_file,
)
from app.logging_config import get_logger
from app.research.claude_cli import find_claude_cli
from app.schemas.app import SettingsUpdate, SettingsView
from app.services import StudyService

router = APIRouter(prefix="/api/settings", tags=["settings"])
log = get_logger("settings")


def _view(service: StudyService, content: SettingsFile) -> SettingsView:
    s = service.settings
    return SettingsView(
        app_dir=str(s.app_dir),
        settings_file=str(settings_path(s.app_dir)),
        data_dir=content.data_dir,
        data_dir_resolved=str(s.data_dir),
        export_dir=content.export_dir,
        export_dir_resolved=str(s.export_dir),
        qualification_min_revenue_usd=content.qualification_min_revenue_usd,
        offline_mode=content.offline_mode,
        offline_forced=os.environ.get("STEAM_STUDY_OFFLINE") == "1",
        steam_api_key_set=bool(content.steam.api_key),
        steam_store_requests_per_minute=content.steam.store_requests_per_minute,
        llm_provider=content.llm.provider,
        llm_model=content.llm.model,
        llm_api_key_set=bool(content.llm.api_key),
        claude_cli_path=content.llm.claude_cli_path,
        claude_cli_detected=str(cli)
        if (cli := find_claude_cli(content.llm.claude_cli_path))
        else None,
        llm_max_budget_usd=content.llm.max_budget_usd,
        llm_timeout_minutes=content.llm.timeout_minutes,
        salary_per_person_year=content.cost_model.salary_per_person_year,
        salary_currency=content.cost_model.salary_currency,
        usd_per_salary_unit=content.cost_model.usd_per_salary_unit,
        comparison_team_size=content.cost_model.comparison_team_size,
        platform_cut_percent=round(content.cost_model.platform_cut * 100, 2),
        warning=s.warning,
    )


@router.get("")
def get_settings(service: Service) -> SettingsView:
    content, _ = read_settings_file(service.settings.app_dir)
    return _view(service, content)


@router.put("")
def update_settings(request: Request, service: Service, body: SettingsUpdate) -> SettingsView:
    app_dir = service.settings.app_dir
    content, _ = read_settings_file(app_dir)
    updated = content.model_copy(deep=True)
    updated.data_dir = body.data_dir.strip()
    updated.export_dir = body.export_dir.strip()
    updated.qualification_min_revenue_usd = body.qualification_min_revenue_usd
    updated.offline_mode = body.offline_mode
    updated.steam.store_requests_per_minute = body.steam_store_requests_per_minute
    updated.llm.provider = body.llm_provider
    updated.llm.model = body.llm_model.strip()
    updated.llm.claude_cli_path = body.claude_cli_path.strip()
    updated.llm.max_budget_usd = body.llm_max_budget_usd
    updated.llm.timeout_minutes = body.llm_timeout_minutes
    updated.cost_model.salary_per_person_year = body.salary_per_person_year
    updated.cost_model.salary_currency = body.salary_currency.strip().upper()
    updated.cost_model.usd_per_salary_unit = body.usd_per_salary_unit
    updated.cost_model.comparison_team_size = body.comparison_team_size
    updated.cost_model.platform_cut = body.platform_cut_percent / 100
    if body.steam_api_key is not None:
        updated.steam.api_key = body.steam_api_key.strip()
    if body.llm_api_key is not None:
        updated.llm.api_key = body.llm_api_key.strip()

    new_settings = settings_from_file(app_dir, updated)
    data_changed = new_settings.data_dir.resolve() != service.settings.data_dir.resolve()
    if data_changed and (service.jobs.running or service.research_jobs.running):
        raise HTTPException(409, "Stop the running data job before changing the data folder.")
    if data_changed:
        try:
            new_settings.data_dir.mkdir(parents=True, exist_ok=True)
            # A new, empty data folder gets a copy of the (read-only) game catalog. Existing
            # studies are NOT moved - the new folder is used as-is.
            if not new_settings.catalog_path.exists() and service.settings.catalog_path.exists():
                shutil.copy2(service.settings.catalog_path, new_settings.catalog_path)
        except OSError as exc:
            raise HTTPException(
                400, f"Cannot use data folder {new_settings.data_dir}: {exc}"
            ) from exc

    write_settings_file(app_dir, updated)
    log.info("settings saved", extra={"data_dir": str(new_settings.data_dir)})

    # Rebuild the service so every change applies immediately (no restart needed).
    state = request.app.state
    new_service = StudyService(new_settings)
    old = cast(StudyService, state.service)
    state.service = new_service
    old.close()
    return _view(new_service, updated)
