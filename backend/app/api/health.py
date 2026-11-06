from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Service
from app.config import APP_VERSION
from app.domain.revenue import LEGACY_MODEL_ID, LEGACY_MODEL_LABEL
from app.schemas.games import (
    DatasetInfo,
    HealthResponse,
    MetaResponse,
    StudyFiltersModel,
)

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(service: Service) -> HealthResponse:
    games = len(service.catalog().games)
    return HealthResponse(
        status="ok" if games else "needs_import",
        version=APP_VERSION,
        schema_version=service.schema_version(),
        games=games,
        message=service.catalog_error,
    )


@router.get("/meta")
def meta(service: Service) -> MetaResponse:
    catalog = service.catalog()
    info = catalog.import_info
    years = list(catalog.year_counts.keys())
    first, last = (years[0], years[-1]) if years else (None, None)
    return MetaResponse(
        dataset=DatasetInfo(
            total_games=len(catalog.games),
            qualified_games=service.qualified_count(),
            qualification_threshold_usd=service.settings.qualification_min_revenue_usd,
            year_counts={str(k): v for k, v in catalog.year_counts.items()},
            source_sha256=info.source_sha256 if info else None,
            imported_at=info.imported_at if info else None,
            scope_label=f"Legacy imported dataset, {first}-{last} releases" if years else "empty",
            revenue_model=LEGACY_MODEL_ID,
            revenue_model_label=LEGACY_MODEL_LABEL,
        ),
        years=years,
        tags=list(catalog.tags),
        default_filters=StudyFiltersModel.from_domain(service.default_filters()),
        default_avoid_repeats=True,
    )
