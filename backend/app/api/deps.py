from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Path, Request

from app.domain.models import LegacyGame
from app.schemas.games import SESSION_ID_PATTERN, GameReport
from app.services import StudyService


def get_service(request: Request) -> StudyService:
    # Looked up per request: changing the data folder in Settings swaps the service.
    return cast(StudyService, request.app.state.service)


Service = Annotated[StudyService, Depends(get_service)]
SessionPath = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]


def require_game(service: StudyService, appid: int) -> LegacyGame:
    game = service.get_game(appid)
    if game is None:
        raise HTTPException(status_code=404, detail=f"AppID {appid} is not in the local database")
    return game


def report(service: StudyService, game: LegacyGame) -> GameReport:
    return GameReport.from_game(
        game,
        service.settings.qualification_min_revenue_usd,
        language=service.language_record(game.appid),
        study=service.studies.get(game.appid),
    )
