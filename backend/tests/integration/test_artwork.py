"""Steam artwork for newer apps: their header image only exists at a hashed CDN path, so the URL
Steam's store data reports is recorded and tried before the AppID-derived paths."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.domain.observations import StoreObservation
from app.providers.steam_store import artwork_urls, fetch_store_info, steam_image_url
from app.services import StudyService
from app.storage.observations import ObservationStore
from tests.conftest import HttpHandler
from tests.fake_steam import FakeApp, FakeSteam

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
HASHED = (
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/3530820/"
    "60ee1e9ebd23297b67cd44a30288199a20186081/header.jpg?t=1793884884"
)


def test_store_info_records_steams_header_url() -> None:
    fake = FakeSteam([FakeApp(3530820, "Puzzling Places", 90, 10, header_image=HASHED)])
    with httpx.Client(transport=httpx.MockTransport(fake)) as client:
        store = fetch_store_info(client, 3530820)
    assert store.header_image == HASHED


def test_only_steam_cdn_https_urls_are_kept() -> None:
    assert steam_image_url(HASHED) == HASHED
    assert steam_image_url("http://shared.akamai.steamstatic.com/x.jpg") == ""  # not https
    assert steam_image_url("https://evil.example.com/steamstatic.com/x.jpg") == ""
    assert steam_image_url("https://steamstatic.com.evil.example/x.jpg") == ""
    assert steam_image_url("javascript:alert(1)") == "" and steam_image_url(None) == ""
    assert steam_image_url(42) == ""


def test_recorded_url_is_tried_first() -> None:
    urls = artwork_urls(3530820, HASHED)
    assert urls[0] == HASHED and len(urls) == 4
    assert artwork_urls(3530820, None) == urls[1:]
    assert artwork_urls(3530820, "https://evil.example.com/x.jpg") == urls[1:]


def test_report_and_export_proxy_use_the_recorded_url(
    online_client_factory: Callable[[HttpHandler], tuple[TestClient, StudyService]],
) -> None:
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        if str(request.url) == HASHED:
            return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})
        return httpx.Response(404)  # the AppID-derived paths do not exist for this app

    client, service = online_client_factory(handler)
    appid = service.catalog().games[0].appid
    assert client.get(f"/api/games/{appid}").json()["header_image"] is None
    service.observations.append(
        StoreObservation(appid, "2026-11-07T10:00:00+00:00", "ok", "game", header_image=HASHED)
    )
    assert client.get(f"/api/games/{appid}").json()["header_image"] == HASHED
    res = client.get(f"/api/games/{appid}/artwork")
    assert res.status_code == 200 and res.content == JPEG
    assert hits == [HASHED]  # straight to the recorded URL, no 404 detours


def test_observation_lines_from_newer_versions_still_load(tmp_path: Path) -> None:
    """A key this version does not know (written by a newer app on another PC) is ignored
    instead of dropping the whole observation."""
    folder = tmp_path / "observations"
    folder.mkdir()
    line = {"kind": "store", "appid": 7, "fetched_at": "2026-11-07T10:00:00+00:00",
            "status": "ok", "name": "Seven", "some_future_field": [1, 2]}  # fmt: skip
    (folder / "steam-otherpc.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    store = ObservationStore(folder).state().store
    assert store[7].name == "Seven" and store[7].header_image == ""
