from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Service, SessionPath, report, require_game
from app.schemas.games import (
    CountResponse,
    GameSummary,
    HistoryResponse,
    SuggestionQuery,
    SuggestionRequest,
    SuggestionResponse,
    ViewRequest,
)

router = APIRouter(prefix="/api", tags=["suggestions"])


@router.post("/suggestions/count")
def count_suggestions(service: Service, body: SuggestionQuery) -> CountResponse:
    result = service.count(
        body.session_id,
        body.filters.to_domain(),
        body.avoid_repeats,
        body.include_below_threshold,
        require_english=body.filters.require_english,
        exclude_studies=body.exclude_studies,
    )
    return CountResponse(
        count=result.count,
        count_ignoring_history=result.count_ignoring_history,
        all_seen=result.all_seen,
    )


@router.post("/suggestions")
def create_suggestion(service: Service, body: SuggestionRequest) -> SuggestionResponse:
    """Uniformly pick one matching game and record it as shown in this session."""
    result = service.suggest(
        body.session_id,
        body.filters.to_domain(),
        body.avoid_repeats,
        body.include_below_threshold,
        body.seed,
        require_english=body.filters.require_english,
        exclude_studies=body.exclude_studies,
    )
    return SuggestionResponse(
        status="ok" if result.game else "no_matches",
        game=report(service, result.game) if result.game else None,
        repeat_history_reset=result.repeat_history_reset,
        candidate_count=result.candidate_count,
    )


@router.get("/sessions/{session_id}/history")
def get_history(service: Service, session_id: SessionPath) -> HistoryResponse:
    return HistoryResponse(items=[GameSummary.from_game(g) for g in service.history(session_id)])


@router.post("/sessions/{session_id}/views")
def record_view(service: Service, session_id: SessionPath, body: ViewRequest) -> HistoryResponse:
    """Record a manual lookup (shown in history and counted as seen, as in the legacy app)."""
    require_game(service, body.appid)
    service.record_manual_view(session_id, body.appid)
    return get_history(service, session_id)


@router.post("/sessions/{session_id}/clear")
def clear_history(service: Service, session_id: SessionPath) -> HistoryResponse:
    service.clear_history(session_id)
    return HistoryResponse(items=[])
