"""JPEG export of a game report (plus the artwork proxy it needs) and the dataset export."""

from __future__ import annotations

import base64
import binascii
import os
import sys

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import Service, require_game
from app.schemas.app import (
    DatasetExportResponse,
    JpegExportRequest,
    JpegExportResponse,
    OpenFolderRequest,
)

router = APIRouter(prefix="/api", tags=["exports"])


@router.get("/games/{appid}/artwork", response_class=Response)
def artwork(service: Service, appid: int) -> Response:
    """Steam header artwork, proxied so the UI can draw it into the exported JPEG (browsers block
    reading cross-origin images into a canvas). Kept in a small in-memory cache only."""
    require_game(service, appid)
    art = service.artwork(appid)
    if art is None:
        raise HTTPException(404, "Artwork unavailable")
    return Response(
        content=art.content, media_type=art.content_type, headers={"Cache-Control": "max-age=3600"}
    )


@router.post("/exports/jpeg")
def export_jpeg(service: Service, body: JpegExportRequest) -> JpegExportResponse:
    game = require_game(service, body.appid)
    payload = body.image_base64.split(",", 1)[-1]  # accept data: URLs too
    try:
        jpeg = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, "image_base64 is not valid base64") from exc
    try:
        path = service.save_export(game, jpeg)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"Could not write the JPEG: {exc}") from exc
    return JpegExportResponse(path=str(path), file_name=path.name, folder=str(path.parent))


@router.post("/exports/dataset")
def export_dataset(service: Service) -> DatasetExportResponse:
    """The whole local dataset as CSV + JSON tables in one zip, for analysis in other tools."""
    try:
        path = service.export_dataset()
    except OSError as exc:
        raise HTTPException(500, f"Could not write the dataset: {exc}") from exc
    return DatasetExportResponse(path=str(path), file_name=path.name, folder=str(path.parent))


@router.post("/system/open-folder", status_code=204)
def open_folder(service: Service, body: OpenFolderRequest) -> Response:
    """Open one of the app's own folders in Explorer (Windows desktop convenience)."""
    folder = {
        "data": service.settings.data_dir,
        "export": service.settings.export_dir,
        "app": service.settings.app_dir,
    }[body.target]
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        raise HTTPException(501, f"Opening folders is only supported on Windows: {folder}")
    os.startfile(folder)
    return Response(status_code=204)
