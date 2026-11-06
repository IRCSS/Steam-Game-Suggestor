"""API contracts for LLM research."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.domain.research import Economics, Range, ResearchFindings
from app.schemas.app import JobView
from app.storage.research import ResearchRun


class RangeView(BaseModel):
    low: float | None
    best: float | None
    high: float | None

    @classmethod
    def of(cls, r: Range) -> RangeView:
        return cls(low=r.low, best=r.best, high=r.high)


class EconomicsView(BaseModel):
    """Derived by the app (not the LLM) from team size x development time and the cost model."""

    person_years: RangeView
    cost: RangeView
    cost_currency: str
    cost_usd: RangeView
    comparison_team_size: int
    comparison_team_years: RangeView
    break_even_gross_usd: RangeView
    break_even_copies: RangeView | None
    price_usd: float
    estimated_revenue_usd: int
    revenue_multiple: float | None
    platform_cut: float
    salary_per_person_year: float
    usd_per_salary_unit: float
    confidence: Literal["high", "medium", "low", "unknown"]

    @classmethod
    def of(
        cls,
        e: Economics,
        *,
        currency: str,
        team: int,
        price: float,
        revenue: int,
        cut: float,
        salary: float,
        rate: float,
    ) -> EconomicsView:
        return cls(
            person_years=RangeView.of(e.person_years),
            cost=RangeView.of(e.cost),
            cost_currency=currency,
            cost_usd=RangeView.of(e.cost_usd),
            comparison_team_size=team,
            comparison_team_years=RangeView.of(e.comparison_team_years),
            break_even_gross_usd=RangeView.of(e.break_even_gross_usd),
            break_even_copies=RangeView.of(e.break_even_copies) if e.break_even_copies else None,
            price_usd=price,
            estimated_revenue_usd=revenue,
            revenue_multiple=e.revenue_multiple,
            platform_cut=cut,
            salary_per_person_year=salary,
            usd_per_salary_unit=rate,
            confidence=e.confidence,
        )


class ResearchRunView(BaseModel):
    created_at: str
    created_by: str
    provider: str
    model: str
    cost_usd: float | None
    duration_seconds: float
    web_searches: int
    reviews_used: dict[str, int]
    warnings: list[str]
    prompt_version: str
    findings: ResearchFindings

    @classmethod
    def of(cls, run: ResearchRun) -> ResearchRunView:
        return cls(
            created_at=run.created_at,
            created_by=run.created_by,
            provider=run.provider,
            model=run.model,
            cost_usd=run.cost_usd,
            duration_seconds=run.duration_seconds,
            web_searches=run.web_searches,
            reviews_used=run.reviews_used,
            warnings=run.warnings,
            prompt_version=run.prompt_version,
            findings=run.findings,
        )


class ResearchView(BaseModel):
    appid: int
    run: ResearchRunView | None
    runs_count: int
    economics: EconomicsView | None


class ResearchStatus(BaseModel):
    available: bool
    message: str
    provider: str
    cli_path: str | None
    max_budget_usd: float
    job: JobView
