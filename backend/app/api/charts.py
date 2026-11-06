"""Charts tab: aggregates over a clearly scoped slice of the local catalog."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import Service, require_game
from app.domain import charts
from app.domain.filters import filter_games
from app.schemas.app import (
    ChartBin,
    ChartPoint,
    ChartsRequest,
    ChartsResponse,
    ChartTag,
    ChartYear,
    HistoryPoint,
    HistoryResponseModel,
    KpiView,
)

router = APIRouter(prefix="/api/charts", tags=["charts"])
MAX_POINTS = 1500


@router.post("/overview")
def overview(service: Service, body: ChartsRequest) -> ChartsResponse:
    floor = service.settings.qualification_min_revenue_usd
    catalog = service.catalog()
    studies = service.studies.appids()
    if body.use_study_filters and body.filters is not None:
        games = service.eligible(
            body.include_below_threshold, body.filters.require_english, exclude_studies=False
        )
        games = filter_games(games, body.filters.to_domain())
        scope = "Games matching the Suggest tab's filters"
    else:
        games = service.eligible(body.include_below_threshold, False, exclude_studies=False)
        if body.years:
            games = [g for g in games if g.release_year in body.years]
        floor_label = "all games" if body.include_below_threshold else f"est. revenue >= ${floor:,}"
        years = ", ".join(str(y) for y in sorted(body.years)) or "all years"
        scope = f"Local catalog ({floor_label}; {years})"
    points = charts.sample(games, MAX_POINTS, keep=studies)
    k = charts.kpis(games)
    return ChartsResponse(
        scope_label=scope,
        as_of=datetime.now(UTC).isoformat(timespec="seconds"),
        catalog_total=len(catalog.games),
        kpis=KpiView(
            count=k.count,
            median_revenue=k.median_revenue,
            median_price=k.median_price,
            median_reviews=k.median_reviews,
            median_score=k.median_score,
        ),
        revenue_bins=[
            ChartBin(start=b.start, end=None if b.end == float("inf") else b.end, count=b.count)
            for b in charts.revenue_histogram(games)
        ],
        points=[
            ChartPoint(
                appid=g.appid,
                name=g.name,
                year=g.release_year,
                price=g.price,
                revenue=g.estimated_revenue,
                reviews=g.total_reviews,
                score=g.review_score,
                in_studies=g.appid in studies,
            )
            for g in points
        ],
        points_total=len(games),
        tags=[
            ChartTag(
                tag=t.tag,
                count=t.count,
                median_revenue=t.median_revenue,
                median_reviews=t.median_reviews,
                median_score=t.median_score,
            )
            for t in charts.tag_stats(games, body.min_tag_count, body.tag_limit)
        ],
        years=[
            ChartYear(year=y.year, count=y.count, median_revenue=y.median_revenue)
            for y in charts.year_stats(games)
        ],
        revenue_model="Estimated gross revenue = total reviews x 45 x listed price (not sales)",
    )


@router.get("/history/{appid}")
def history(service: Service, appid: int) -> HistoryResponseModel:
    """Review/revenue snapshots for one game: the legacy import (date unknown) plus every
    Steam refresh. Fewer than two dated points means there is no trend to show yet."""
    game = require_game(service, appid)
    legacy = next((g for g in service.legacy_games() if g.appid == appid), None)
    points: list[HistoryPoint] = []
    if legacy is not None:
        points.append(
            HistoryPoint(
                observed_at=None,
                source="legacy_import",
                total_reviews=legacy.total_reviews,
                estimated_revenue=legacy.estimated_revenue,
            )
        )
    price = game.price
    for obs in sorted(
        service.observations.state().review_history.get(appid, []), key=lambda o: o.fetched_at
    ):
        points.append(
            HistoryPoint(
                observed_at=obs.fetched_at,
                source="steam_reviews_all_languages",
                total_reviews=obs.total_reviews,
                estimated_revenue=round(obs.total_reviews * 45 * price),
            )
        )
    dated = sum(1 for p in points if p.observed_at)
    return HistoryResponseModel(
        appid=appid, name=game.name, points=points, enough_history=dated >= 2
    )
