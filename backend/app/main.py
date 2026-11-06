"""FastAPI application factory. Run with: uv run uvicorn app.main:app --host 127.0.0.1"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import games, health, suggestions
from app.config import APP_VERSION, REPO_ROOT, Settings, load_settings
from app.logging_config import configure_logging, get_logger
from app.services import StudyService

log = get_logger("http")
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _is_local_origin(origin: str) -> bool:
    try:
        return urlparse(origin).hostname in _LOCAL_HOSTS
    except ValueError:
        return False


def create_app(settings: Settings | None = None, service: StudyService | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.service = service or StudyService(settings)
        yield
        if service is None:
            app.state.service.close()

    app = FastAPI(title="Steam Study Tool API", version=APP_VERSION, lifespan=lifespan)

    @app.middleware("http")
    async def guard_and_trace(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        # CSRF / hostile-origin guard: state-changing requests must come from a local origin.
        origin = request.headers.get("origin")
        if request.method not in _SAFE_METHODS and origin and not _is_local_origin(origin):
            log.warning("blocked cross-origin write", extra={"origin": origin, "rid": request_id})
            return JSONResponse({"detail": "cross-origin request blocked"}, status_code=403)
        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            log.info(
                "request",
                extra={
                    "rid": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health.router)
    app.include_router(games.router)
    app.include_router(suggestions.router)

    # Serve the built UI from the same origin when available (`npm run build` first).
    if (FRONTEND_DIST / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = (FRONTEND_DIST / path).resolve()
            if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
