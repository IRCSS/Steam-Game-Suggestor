from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import Service, report, require_game
from app.domain.lookup import AUTOCOMPLETE_LIMIT
from app.schemas.games import GameReport, GameSearchResponse, GameSummary

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("")
def search_games(
    service: Service,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = AUTOCOMPLETE_LIMIT,
) -> GameSearchResponse:
    """Name/AppID search (legacy autocomplete). Ignores study filters and qualification."""
    return GameSearchResponse(items=[GameSummary.from_game(g) for g in service.search(q, limit)])


@router.get("/resolve")
def resolve_game(
    service: Service, q: Annotated[str, Query(min_length=1, max_length=200)]
) -> GameReport:
    """Legacy 'Load game report': exact AppID, exact name, then best name match."""
    game = service.resolve(q)
    if game is None:
        raise HTTPException(status_code=404, detail="No matching game found.")
    return report(service, game)


@router.get("/{appid}")
def get_game(service: Service, appid: int) -> GameReport:
    return report(service, require_game(service, appid))
