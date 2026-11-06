"""Studies: games archived as potential case studies (one JSON file per game)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Service, report, require_game
from app.schemas.app import StudiesResponse, StudyItem
from app.schemas.games import GameReport

router = APIRouter(prefix="/api/studies", tags=["studies"])


@router.get("")
def list_studies(service: Service) -> StudiesResponse:
    catalog = service.catalog()
    items: list[StudyItem] = []
    for study in service.list_studies():
        game = catalog.by_appid.get(study.appid)
        items.append(
            StudyItem(
                appid=study.appid,
                name=game.name if game else study.name,
                added_at=study.added_at,
                added_by=study.added_by,
                release_year=game.release_year if game else None,
                estimated_revenue_usd=game.estimated_revenue if game else None,
            )
        )
    return StudiesResponse(items=items, folder=str(service.settings.studies_dir))


@router.put("/{appid}")
def add_study(service: Service, appid: int) -> GameReport:
    """Archive a game as a study. It is skipped by future suggestions (when that switch is on)."""
    game = require_game(service, appid)
    service.add_study(game)
    return report(service, game)


@router.delete("/{appid}")
def remove_study(service: Service, appid: int) -> GameReport:
    game = require_game(service, appid)
    service.remove_study(appid)
    return report(service, game)
