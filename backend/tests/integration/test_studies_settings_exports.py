from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import Settings, read_settings_file, settings_path
from app.domain.languages import LanguageRecord
from app.services import StudyService, export_filename
from app.storage.language_cache import LanguageCache
from app.storage.studies import StudyStore
from tests.conftest import HttpHandler, make_settings

SESSION = "studies-session-01"


def no_sleep(_seconds: float) -> None:
    return None


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def defaults(client: TestClient) -> dict[str, Any]:
    return client.get("/api/meta").json()["default_filters"]


def query(client: TestClient, **overrides: Any) -> dict[str, Any]:
    filters = {**defaults(client), **overrides.pop("filters", {})}
    return {"session_id": SESSION, "filters": filters, **overrides}


def pool(client: TestClient) -> list[int]:
    """All AppIDs matching the default filters (sample DB), via repeated seeded suggestions."""
    body = query(client, avoid_repeats=True, exclude_studies=False)
    total = client.post("/api/suggestions/count", json=body).json()["count"]
    out: list[int] = []
    session = "pool-session-1"
    for i in range(total):
        res = client.post(
            "/api/suggestions", json={**body, "session_id": session, "seed": i}
        ).json()
        out.append(res["game"]["appid"])
    return out


# --- studies ---------------------------------------------------------------------------------


def test_add_to_studies_persists_as_file_and_is_skipped(
    sample_client: TestClient, sample_settings: Settings
) -> None:
    candidates = pool(sample_client)
    target = candidates[0]
    res = sample_client.put(f"/api/studies/{target}").json()
    assert res["study"]["in_studies"] is True and res["study"]["added_by"]
    study_file = sample_settings.studies_dir / f"{target}.json"
    data = json.loads(study_file.read_text(encoding="utf-8"))
    assert data["appid"] == target and data["status"] == "study"

    # Skipped by suggestions (default), still reachable by lookup.
    before = sample_client.post(
        "/api/suggestions/count", json=query(sample_client, exclude_studies=False)
    ).json()["count"]
    after = sample_client.post("/api/suggestions/count", json=query(sample_client)).json()["count"]
    assert after == before - 1
    for seed in range(40):
        body = {**query(sample_client), "session_id": f"skip-session-{seed:03d}", "seed": seed}
        assert sample_client.post("/api/suggestions", json=body).json()["game"]["appid"] != target
    assert sample_client.get(f"/api/games/{target}").json()["study"]["in_studies"] is True

    items = sample_client.get("/api/studies").json()["items"]
    assert [i["appid"] for i in items] == [target]

    # Adding twice is a no-op; removing deletes the file.
    sample_client.put(f"/api/studies/{target}")
    assert len(list(sample_settings.studies_dir.glob("*.json"))) == 1
    removed = sample_client.delete(f"/api/studies/{target}").json()
    assert removed["study"]["in_studies"] is False and not study_file.exists()
    assert sample_client.put("/api/studies/1").status_code == 404


def test_studies_written_by_another_pc_are_picked_up(tmp_path: Path) -> None:
    folder = tmp_path / "studies"
    mine, other_pc = StudyStore(folder), StudyStore(folder)
    assert mine.appids() == frozenset()
    other_pc.add(42, "Other PC's study")
    mine._loaded_at = time.monotonic() - 60  # cache window elapsed
    assert mine.appids() == frozenset({42})
    (folder / "broken.json").write_text("{not json", encoding="utf-8")
    mine._loaded_at = 0
    assert mine.appids() == frozenset({42})  # unreadable files are skipped, not fatal


# --- settings --------------------------------------------------------------------------------


def test_settings_file_created_with_defaults(tmp_path: Path) -> None:
    content, warning = read_settings_file(tmp_path)
    assert warning is None and settings_path(tmp_path).is_file()
    assert content.data_dir == "data" and content.export_dir == "studiesJPG"
    assert content.qualification_min_revenue_usd == 100_000


def test_invalid_settings_file_is_set_aside(tmp_path: Path) -> None:
    settings_path(tmp_path).write_text("{oops", encoding="utf-8")
    content, warning = read_settings_file(tmp_path)
    assert warning and "invalid" in warning
    assert content.data_dir == "data"
    assert list(tmp_path.glob("settings.invalid-*.json"))


def test_unknown_settings_keys_preserved(tmp_path: Path) -> None:
    settings_path(tmp_path).write_text(json.dumps({"future_key": 1, "data_dir": "x"}), "utf-8")
    content, _ = read_settings_file(tmp_path)
    assert content.model_dump()["future_key"] == 1 and content.data_dir == "x"


def test_settings_api_round_trip_and_secrets_hidden(
    sample_client: TestClient, sample_settings: Settings
) -> None:
    view = sample_client.get("/api/settings").json()
    assert view["data_dir"] == "data" and view["steam_api_key_set"] is False
    update = {
        "data_dir": "data",
        "export_dir": "exports/jpg",
        "qualification_min_revenue_usd": 150_000,
        "offline_mode": True,
        "steam_store_requests_per_minute": 20,
        "llm_provider": "openai",
        "llm_model": "some-model",
        "steam_api_key": "SECRET-STEAM",
        "llm_api_key": "SECRET-LLM",
    }
    res = sample_client.put("/api/settings", json=update, headers={"Origin": "http://127.0.0.1"})
    assert res.status_code == 200
    body = res.json()
    assert "SECRET" not in res.text
    assert body["steam_api_key_set"] and body["llm_api_key_set"]
    assert body["export_dir_resolved"] == str(sample_settings.app_dir / "exports" / "jpg")
    stored = json.loads(settings_path(sample_settings.app_dir).read_text(encoding="utf-8"))
    assert stored["steam"]["api_key"] == "SECRET-STEAM" and stored["llm"]["provider"] == "openai"
    # Applies immediately: qualification floor changed.
    assert (
        sample_client.get("/api/meta").json()["dataset"]["qualification_threshold_usd"] == 150_000
    )
    # Omitting keys keeps them; "" clears them.
    keep = {k: v for k, v in update.items() if not k.endswith("api_key")}
    assert sample_client.put("/api/settings", json=keep).json()["steam_api_key_set"] is True
    cleared = sample_client.put("/api/settings", json={**keep, "steam_api_key": ""}).json()
    assert cleared["steam_api_key_set"] is False


def test_changing_data_folder_copies_catalog_only(
    sample_client: TestClient, sample_settings: Settings, tmp_path: Path
) -> None:
    game = pool(sample_client)[0]
    sample_client.put(f"/api/studies/{game}")
    new_dir = tmp_path / "shared" / "studydata"
    body = {
        "data_dir": str(new_dir),
        "export_dir": "studiesJPG",
        "qualification_min_revenue_usd": 100_000,
        "offline_mode": True,
        "steam_store_requests_per_minute": 35,
        "llm_provider": "none",
    }
    view = sample_client.put("/api/settings", json=body).json()
    assert view["data_dir_resolved"] == str(new_dir)
    assert (new_dir / "catalog.sqlite3").is_file()
    assert sample_client.get("/api/health").json()["games"] == 55
    assert sample_client.get("/api/studies").json()["items"] == []  # studies are not moved
    assert (sample_settings.studies_dir / f"{game}.json").is_file()  # old data untouched


# --- languages -------------------------------------------------------------------------------


def test_language_cache_merges_shards_from_several_pcs(tmp_path: Path) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    (folder / "languages-pc-a.jsonl").write_text(
        json.dumps(
            {"appid": 1, "status": "ok", "languages": ["Japanese"], "fetched_at": "2026-01-01"}
        )
        + "\n"
        + '{"appid": 2, "status": "ok", "langu',  # truncated line mid-sync
        encoding="utf-8",
    )
    (folder / "languages-pc-b.jsonl").write_text(
        json.dumps(
            {"appid": 1, "status": "ok", "languages": ["English"], "fetched_at": "2026-02-01"}
        )
        + "\n",
        encoding="utf-8",
    )
    cache = LanguageCache(folder)
    records = cache.records()
    assert set(records) == {1} and records[1].languages == ("English",)  # newest wins
    cache.append(LanguageRecord(5, "unavailable", (), "2026-03-01"))
    assert cache.own_file.exists() and 5 in LanguageCache(folder).records()


# --- exports ---------------------------------------------------------------------------------


def test_export_filename_is_safe() -> None:
    assert export_filename('A: "Game" / Part 2?', 7) == "A   Game    Part 2 (7).jpg"
    assert export_filename("", 9) == "game (9).jpg"
    assert len(export_filename("x" * 300, 1)) <= 80 + len(" (1).jpg")


def test_export_jpeg_saves_to_export_folder(
    sample_client: TestClient, sample_settings: Settings
) -> None:
    appid = pool(sample_client)[0]
    payload = {
        "appid": appid,
        "image_base64": "data:image/jpeg;base64," + base64.b64encode(JPEG).decode(),
    }
    res = sample_client.post("/api/exports/jpeg", json=payload)
    assert res.status_code == 200
    path = Path(res.json()["path"])
    assert path.parent == sample_settings.export_dir and path.read_bytes() == JPEG
    # Re-export overwrites the same file (one JPG per game).
    sample_client.post("/api/exports/jpeg", json=payload)
    assert len(list(sample_settings.export_dir.glob("*.jpg"))) == 1


def test_export_rejects_non_jpeg_and_bad_base64(sample_client: TestClient) -> None:
    appid = pool(sample_client)[0]
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    assert (
        sample_client.post(
            "/api/exports/jpeg", json={"appid": appid, "image_base64": png}
        ).status_code
        == 400
    )
    bad = sample_client.post("/api/exports/jpeg", json={"appid": appid, "image_base64": "@@@"})
    assert bad.status_code == 400
    missing = {"appid": 1, "image_base64": base64.b64encode(JPEG).decode()}
    assert sample_client.post("/api/exports/jpeg", json=missing).status_code == 404


def test_artwork_proxy(
    online_client_factory: Callable[[HttpHandler], tuple[TestClient, StudyService]],
) -> None:
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        if "capsule_616x353" in str(request.url):
            return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})
        return httpx.Response(404)

    client, service = online_client_factory(handler)
    appid = service.catalog().games[0].appid
    res = client.get(f"/api/games/{appid}/artwork")
    assert res.status_code == 200 and res.content == JPEG
    assert res.headers["content-type"] == "image/jpeg"
    client.get(f"/api/games/{appid}/artwork")
    assert len(hits) == 2  # header 404 -> capsule 200, then served from memory cache


def test_artwork_offline_is_404(sample_client: TestClient) -> None:
    appid = pool(sample_client)[0]
    assert sample_client.get(f"/api/games/{appid}/artwork").status_code == 404


def test_make_settings_layout(tmp_path: Path) -> None:
    s = make_settings(tmp_path)
    assert s.catalog_path == tmp_path / "data" / "catalog.sqlite3"
    assert s.studies_dir == tmp_path / "data" / "studies"


def test_settings_v1_migrates_placeholder_llm_provider(tmp_path: Path) -> None:
    old = {
        "version": 1,
        "data_dir": "data",
        "llm": {"provider": "none", "model": "", "api_key": ""},
    }
    settings_path(tmp_path).write_text(json.dumps(old), encoding="utf-8")
    content, _ = read_settings_file(tmp_path)
    assert content.version == 2 and content.llm.provider == "claude_code"
    stored = json.loads(settings_path(tmp_path).read_text(encoding="utf-8"))
    assert stored["llm"]["provider"] == "claude_code" and stored["version"] == 2
    # A deliberate "off" after the upgrade is respected.
    stored["llm"]["provider"] = "none"
    settings_path(tmp_path).write_text(json.dumps(stored), encoding="utf-8")
    assert read_settings_file(tmp_path)[0].llm.provider == "none"
