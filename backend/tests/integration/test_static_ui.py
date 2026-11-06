"""The packaged app / `npm run start` serve the built UI from FastAPI. Regression: on Windows the
registry can map .js to text/plain, which makes the browser refuse to run the app (blank window).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import StudyService
from tests.conftest import make_settings


@pytest.fixture
def ui_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>Indie Case Study Suggester</title>"
        '<script type="module" src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("export {};", encoding="utf-8")
    (dist / "assets" / "app.css").write_text("body{}", encoding="utf-8")
    monkeypatch.setenv("STEAM_STUDY_FRONTEND_DIST", str(dist))
    # Simulate the broken Windows registry mapping; create_app must repair it.
    mimetypes.add_type("text/plain", ".js")
    mimetypes.add_type("text/plain", ".css")
    assert mimetypes.guess_type("x.js")[0] == "text/plain"
    settings = make_settings(tmp_path)
    return TestClient(create_app(settings, StudyService(settings)))


def test_assets_served_with_web_mime_types(ui_client: TestClient) -> None:
    js = ui_client.get("/assets/app.js")
    assert js.status_code == 200
    assert js.headers["content-type"].startswith("text/javascript")
    assert ui_client.get("/assets/app.css").headers["content-type"].startswith("text/css")


def test_spa_fallback_and_api_404(ui_client: TestClient) -> None:
    assert "<title>Indie Case Study Suggester</title>" in ui_client.get("/").text
    assert "<title>" in ui_client.get("/some/deep/link").text
    assert ui_client.get("/api/does-not-exist").status_code == 404
