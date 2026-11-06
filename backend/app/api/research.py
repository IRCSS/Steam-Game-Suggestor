"""LLM research per game ("Get more info from LLM")."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.data import job_view
from app.api.deps import Service, require_game
from app.schemas.app import JobView
from app.schemas.research import EconomicsView, ResearchRunView, ResearchStatus, ResearchView
from app.services import OfflineError

router = APIRouter(prefix="/api/research", tags=["research"])


# Fixed paths first: /job must not be parsed as an AppID.
@router.get("/status")
def research_status(service: Service) -> ResearchStatus:
    available, message = service.research_availability()
    cli = service.research_cli()
    return ResearchStatus(
        available=available,
        message=message,
        provider=service.settings.llm_provider,
        cli_path=str(cli) if cli else None,
        max_budget_usd=service.settings.llm_max_budget_usd,
        job=job_view(service.research_jobs.status),
    )


@router.get("/job")
def research_job(service: Service) -> JobView:
    return job_view(service.research_jobs.status)


@router.post("/job/cancel")
def cancel_research(service: Service) -> JobView:
    service.research_jobs.cancel()
    return job_view(service.research_jobs.status)


@router.get("/{appid}")
def get_research(service: Service, appid: int) -> ResearchView:
    game = require_game(service, appid)
    record = service.research.load(appid)
    run = record.runs[-1] if record and record.runs else None
    economics = None
    if run is not None:
        m = service.settings.cost_model
        economics = EconomicsView.of(
            service.economics(game, run),
            currency=m.salary_currency,
            team=m.comparison_team_size,
            price=game.price,
            revenue=game.estimated_revenue,
            cut=m.platform_cut,
            salary=m.salary_per_person_year,
            rate=m.usd_per_salary_unit,
        )
    return ResearchView(
        appid=appid,
        run=ResearchRunView.of(run) if run else None,
        runs_count=len(record.runs) if record else 0,
        economics=economics,
    )


@router.post("/{appid}")
def start_research(service: Service, appid: int) -> JobView:
    """Start (or refresh) research for one game. Earlier runs are kept."""
    game = require_game(service, appid)
    try:
        started = service.start_research(game)
    except OfflineError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not started:
        raise HTTPException(409, "Another research run is in progress.")
    return job_view(service.research_jobs.status)
