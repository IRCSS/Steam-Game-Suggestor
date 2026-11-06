"""FastAPI application factory. Run with: uv run uvicorn app.main:app --host 127.0.0.1"""

from __future__ import annotations

import mimetypes
import os
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import charts, data, exports, games, health, languages, studies, suggestions
from app.api import settings as settings_api
from app.config import APP_VERSION, REPO_ROOT, Settings, load_settings
from app.logging_config import configure_logging, get_logger
from app.services import StudyService

log = get_logger("http")


def register_web_mimetypes() -> None:
    """Python's mimetypes reads the Windows registry, which on many machines maps .js to
    text/plain. Browsers refuse to run <script type="module"> served as text/plain (the packaged
    app showed a blank window), so pin the web types every time an app is created."""
    for type_, ext in (
        ("text/javascript", ".js"),
        ("text/javascript", ".mjs"),
        ("text/css", ".css"),
        ("image/svg+xml", ".svg"),
        ("application/json", ".json"),
    ):
        mimetypes.add_type(type_, ext)


def _frontend_dist() -> Path:
    # The packaged desktop app points this at its bundled copy of the built UI.
    override = os.environ.get("STEAM_STUDY_FRONTEND_DIST")
    return Path(override) if override else REPO_ROOT / "frontend" / "dist"


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
    register_web_mimetypes()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.service = service or StudyService(settings)
        yield
        # Close whatever service is current (Settings may have swapped it), unless the caller
        # passed in its own service and still owns it.
        if app.state.service is not service:
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
    app.include_router(studies.router)
    app.include_router(languages.router)
    app.include_router(exports.router)
    app.include_router(settings_api.router)
    app.include_router(data.router)
    app.include_router(charts.router)

    # Serve the built UI from the same origin when available (`npm run build` first).
    FRONTEND_DIST = _frontend_dist()
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
