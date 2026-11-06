"""Data tab: observations overlay, ranks, providers, refresh/discover/single jobs, charts."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, read_settings_file, write_settings_file
from app.domain.observations import (
    ReviewsObservation,
    StoreObservation,
    TagsObservation,
    build_catalog,
    parse_release_year,
)
from app.domain.ranks import compute_ranks
from app.main import create_app
from app.providers.steam_store import StoreError, fetch_app_list, fetch_reviews, fetch_store_info
from app.services import StudyService
from app.storage.observations import ObservationStore
from tests.conftest import import_sample, make_settings
from tests.fake_steam import API_KEY, FakeApp, FakeSteam
from tests.helpers import game

# --- pure domain -------------------------------------------------------------------------------


def test_compute_ranks_matches_legacy_rule() -> None:
    games = [
        game(appid=1, release_year=2023, estimated_revenue=500, total_reviews=30, source_index=0),
        game(appid=2, release_year=2023, estimated_revenue=900, total_reviews=30, source_index=1),
        game(appid=3, release_year=2023, estimated_revenue=500, total_reviews=30, source_index=2),
        game(appid=4, release_year=2023, estimated_revenue=999, total_reviews=19, source_index=3),
    ]
    ranked = {g.appid: g for g in compute_ranks(games)}
    assert [ranked[a].revenue_rank_in_year for a in (2, 1, 3)] == [1, 2, 3]  # ties: source order
    assert ranked[2].qualifying_games_in_year == 3  # < 20 reviews is outside the population
    assert ranked[2].revenue_percentile_in_year == 100.0
    assert ranked[3].revenue_percentile_in_year == round(100 * 1 / 3, 2)
    assert ranked[4].revenue_rank_in_year == 0


def test_parse_release_year() -> None:
    assert parse_release_year("Oct 20, 2022") == 2022
    assert parse_release_year("20 Oct, 2022") == 2022
    assert parse_release_year("Q1 2026") == 2026
    assert parse_release_year("Coming soon") is None


def test_build_catalog_overlays_and_adds_new_games() -> None:
    legacy = compute_ranks(
        [game(appid=1, price=10.0, total_reviews=1000, estimated_revenue=450_000)]
    )
    untouched = build_catalog(legacy, {}, {}, {})
    assert untouched == legacy and untouched[0].data_source == "legacy_import"

    reviews = {1: ReviewsObservation(1, "2026-11-06T10:00:00+00:00", 2000, 1900, 100)}
    store = {
        1: StoreObservation(1, "2026-11-06T10:00:00+00:00", "ok", "game", "Renamed", "Pitch",
                            False, 1499, "USD", "May 1, 2023", 2023),
        9: StoreObservation(9, "2026-11-06T10:00:00+00:00", "ok", "game", "New Game", "",
                            False, 2000, "USD", "Jan 5, 2026", 2026),
        8: StoreObservation(8, "2026-11-06T10:00:00+00:00", "ok", "game", "No reviews yet", "",
                            False, 2000, "USD", "Jan 5, 2026", 2026),
    }  # fmt: skip
    reviews[9] = ReviewsObservation(9, "2026-11-06T10:00:00+00:00", 500, 450, 50)
    tags = {9: TagsObservation(9, "2026-11-06T10:00:00+00:00", ("Indie", "Cozy"))}
    merged = {g.appid: g for g in build_catalog(legacy, store, reviews, tags)}
    old = merged[1]
    assert old.data_source == "steam" and old.name == "Renamed"
    assert old.total_reviews == 2000 and old.review_score == 95.0 and old.price == 14.99
    assert old.estimated_revenue == round(2000 * 45 * 14.99)
    assert old.legacy_rank_in_year is None or old.legacy_rank_in_year >= 0
    new = merged[9]
    assert new.data_source == "steam_new" and new.release_year == 2026
    assert new.tags == ("Indie", "Cozy") and new.estimated_revenue == 450_000
    assert new.revenue_rank_in_year == 1
    assert 8 not in merged  # store info without reviews is not a catalog game


def test_observation_store_merges_shards_and_partial_lines(tmp_path: Path) -> None:
    folder = tmp_path / "observations"
    folder.mkdir()
    old = {"kind": "reviews", "appid": 5, "fetched_at": "2026-01-01", "total_reviews": 10,
           "total_positive": 9, "total_negative": 1}  # fmt: skip
    new = {**old, "fetched_at": "2026-02-01", "total_reviews": 30, "total_positive": 27}
    (folder / "steam-pc-a.jsonl").write_text(json.dumps(old) + "\n" + '{"kind": "rev', "utf-8")
    (folder / "steam-pc-b.jsonl").write_text(json.dumps(new) + "\n", "utf-8")
    store = ObservationStore(folder)
    state = store.state()
    assert state.reviews[5].total_reviews == 30
    assert [o.total_reviews for o in state.review_history[5]] == [10, 30] or [
        o.total_reviews for o in state.review_history[5]
    ] == [30, 10]
    # The half-synced line completes later -> picked up incrementally.
    with (folder / "steam-pc-a.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('iews", "appid": 6, "fetched_at": "2026-03-01", "total_reviews": 1, '
                     '"total_positive": 1, "total_negative": 0}\n')  # fmt: skip
    store.refresh(force=True)
    assert 6 in store.state().reviews


# --- providers (wire format) -------------------------------------------------------------------


def fake_client(fake: FakeSteam) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake))


def test_providers_parse_and_request_all_languages() -> None:
    fake = FakeSteam([FakeApp(10, "Ten", 900, 100, price_cents=1999, release="Oct 20, 2022")])
    with fake_client(fake) as client:
        store = fetch_store_info(client, 10)
        reviews = fetch_reviews(client, 10)
        missing = fetch_store_info(client, 11)
    assert (store.status, store.price_cents, store.release_year) == ("ok", 1999, 2022)
    assert store.languages == ("English", "French")
    assert (reviews.total_reviews, reviews.review_score) == (1000, 90.0)
    assert fake.review_queries[0]["languages"] == ["all"]  # not the English-only default
    assert missing.status == "unavailable"


def test_app_list_requires_key_and_never_leaks_it() -> None:
    fake = FakeSteam([FakeApp(10, "Ten", 1, 0)])
    with fake_client(fake) as client:
        with pytest.raises(StoreError) as missing:
            fetch_app_list(client, "", 0)
        with pytest.raises(StoreError) as wrong:
            fetch_app_list(client, "WRONG-SECRET", 0)
        page = fetch_app_list(client, API_KEY, 0)
    assert "key" in str(missing.value)
    assert "WRONG-SECRET" not in str(wrong.value) and "403" in str(wrong.value)
    assert [a.appid for a in page.apps] == [10]


# --- jobs through the API ----------------------------------------------------------------------


@pytest.fixture
def online(tmp_path: Path) -> Iterator[Callable[[FakeSteam], tuple[TestClient, StudyService]]]:
    clients: list[TestClient] = []

    def build(fake: FakeSteam, api_key: str = API_KEY) -> tuple[TestClient, StudyService]:
        settings: Settings = make_settings(tmp_path, offline=False, rpm=120)
        import_sample(settings)
        content, _ = read_settings_file(tmp_path)
        content.steam.api_key = api_key
        write_settings_file(tmp_path, content)
        service = StudyService(settings, http_factory=lambda: fake_client(fake))
        service.jobs._sleep = lambda _s: None  # no real waiting in tests
        client = TestClient(create_app(settings, service))
        client.__enter__()
        clients.append(client)
        return client, service

    yield build
    for client in clients:
        client.__exit__(None, None, None)


def wait_job(client: TestClient, timeout: float = 20) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get("/api/data/jobs/current").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def sample_apps(service: StudyService) -> list[FakeApp]:
    return [
        FakeApp(g.appid, g.name, g.total_reviews * 2, 0, price_cents=round(g.price * 100) or 999)
        for g in service.catalog().games
    ]


def test_refresh_updates_qualified_games_and_skips_fresh(
    online: Callable[[FakeSteam], tuple[TestClient, StudyService]],
) -> None:
    fake = FakeSteam([])
    client, service = online(fake)
    fake.apps = {a.appid: a for a in sample_apps(service)}
    qualified = service.qualified_count()
    body = {"kind": "refresh", "refresh": {"scope": "qualified", "parts": ["reviews", "store"]}}
    preview = client.post("/api/data/jobs/preview", json=body).json()
    assert preview["items"] == qualified and preview["requests"] == 2 * qualified
    assert client.post("/api/data/jobs", json=body).status_code == 200
    job = wait_job(client)
    assert job["state"] == "completed" and job["counters"]["reviews_updated"] == qualified
    assert fake.calls["reviews"] == qualified and fake.calls["store"] == qualified

    status = client.get("/api/data/status").json()
    assert status["refreshed"] == qualified and status["last_update"]
    refreshed = next(g for g in service.catalog().games if g.data_source == "steam")
    report = client.get(f"/api/games/{refreshed.appid}").json()
    assert report["provenance"]["data_source"] == "steam"
    assert (
        report["reviews"]["observed_at"]
        and report["reviews"]["source"] == "steam_reviews_all_languages"
    )
    assert report["rank"]["scope_label"].startswith("local catalog")
    assert report["languages"]["english"] is True  # languages come with store details

    # A second run within stale_days fetches nothing.
    assert client.post("/api/data/jobs/preview", json=body).json()["items"] == 0
    # Study files are untouched by data jobs.
    assert not service.settings.studies_dir.exists()


def test_refresh_scope_years_and_studies(
    online: Callable[[FakeSteam], tuple[TestClient, StudyService]],
) -> None:
    client, service = online(FakeSteam([]))
    games = service.catalog().games
    in_2024 = sum(1 for g in games if g.release_year == 2024)
    body = {"kind": "refresh", "refresh": {"scope": "all", "years": [2024], "parts": ["reviews"]}}
    assert client.post("/api/data/jobs/preview", json=body).json()["items"] == in_2024
    client.put(f"/api/studies/{games[0].appid}")
    studies = {"kind": "refresh", "refresh": {"scope": "studies", "parts": ["reviews", "tags"]}}
    assert client.post("/api/data/jobs/preview", json=studies).json()["items"] == 1
    languages = {"kind": "languages", "refresh": {"scope": "all"}}
    assert client.post("/api/data/jobs/preview", json=languages).json()["items"] == len(games)


def test_retries_429_then_succeeds(
    online: Callable[[FakeSteam], tuple[TestClient, StudyService]],
) -> None:
    fake = FakeSteam([])
    client, service = online(fake)
    fake.apps = {a.appid: a for a in sample_apps(service)}
    fake.flaky["reviews"] = 2
    waits: list[float] = []
    service.jobs._sleep = waits.append
    target = service.catalog().games[0].appid
    client.post("/api/data/jobs", json={"kind": "app", "appid": target})
    job = wait_job(client)
    assert job["state"] == "completed" and job["counters"].get("errors", 0) == 0
    assert job["counters"]["retries"] == 2 and 3.0 in waits  # honoured Retry-After


def test_discover_lists_after_last_appid_and_screens(
    online: Callable[[FakeSteam], tuple[TestClient, StudyService]],
) -> None:
    fake = FakeSteam([])
    client, service = online(fake)
    top = max(g.appid for g in service.catalog().games)
    fake.apps = {
        top - 5: FakeApp(top - 5, "Old listed", 10, 0),  # below cursor: never screened
        top + 1: FakeApp(top + 1, "Hit", 900, 100, price_cents=1999),  # 1000*45*19.99 ~ $900K
        top + 2: FakeApp(top + 2, "Tiny", 3, 0),  # 3*45*70 < $100K -> no store call
        top + 3: FakeApp(top + 3, "Soundtrack", 5000, 0, app_type="music"),
        top + 4: FakeApp(top + 4, "Free", 9000, 0, is_free=True),
    }
    assert client.post("/api/data/test-key").json()["ok"] is True
    client.post("/api/data/jobs", json={"kind": "discover", "discover": {"max_new": 50}})
    job = wait_job(client)
    assert job["state"] == "completed", job
    c = job["counters"]
    assert c["listed"] == 4 and c["screened"] == 4 and c["added_qualified"] == 1
    assert c["below_floor"] == 2 and c["not_released_or_not_game"] == 1
    assert fake.calls["store"] == 3  # Tiny was screened out by reviews alone
    hit = client.get(f"/api/games/{top + 1}").json()
    assert hit["provenance"]["data_source"] == "steam_new" and hit["qualification"]["qualified"]
    assert hit["tags"] == ["Indie", "Roguelike"]
    assert all(k == API_KEY for k in fake.seen_key_values)
    status = client.get("/api/data/status").json()
    assert status["discovered"] >= 1 and status["discovery_cursor_appid"] == top + 4
    # Nothing left to do on the next run.
    client.post("/api/data/jobs", json={"kind": "discover"})
    assert wait_job(client)["counters"].get("screened", 0) == 0


def test_discover_without_key_is_refused(
    online: Callable[..., tuple[TestClient, StudyService]],
) -> None:
    client, _ = online(FakeSteam([]), "")
    res = client.post("/api/data/jobs", json={"kind": "discover"})
    assert res.status_code == 409 and "API key" in res.json()["detail"]
    assert client.post("/api/data/jobs/preview", json={"kind": "discover"}).json()["needs_key"]
    assert client.post("/api/data/test-key").json()["ok"] is False


def test_jobs_refused_offline_and_one_at_a_time(sample_client: TestClient) -> None:
    res = sample_client.post("/api/data/jobs", json={"kind": "refresh"})
    assert res.status_code == 409 and "Offline" in res.json()["detail"]
    assert sample_client.get("/api/data/jobs/current").json()["state"] == "idle"


# --- charts -------------------------------------------------------------------------------------


def test_charts_overview_counts_are_consistent(sample_client: TestClient) -> None:
    res = sample_client.post("/api/charts/overview", json={}).json()
    qualified = sample_client.get("/api/meta").json()["dataset"]["qualified_games"]
    assert res["kpis"]["count"] == qualified == res["points_total"]
    assert sum(b["count"] for b in res["revenue_bins"]) == qualified
    assert res["revenue_bins"][0]["start"] >= 100_000 or res["revenue_bins"][0]["count"] == 0
    assert sum(y["count"] for y in res["years"]) == qualified
    assert "est. revenue >= $100,000" in res["scope_label"]
    wide = sample_client.post("/api/charts/overview", json={"include_below_threshold": True}).json()
    assert wide["kpis"]["count"] == 55
    year = sample_client.post("/api/charts/overview", json={"years": [2023]}).json()
    assert all(p["year"] == 2023 for p in year["points"])


def test_charts_with_study_filters(sample_client: TestClient) -> None:
    filters = sample_client.get("/api/meta").json()["default_filters"]
    res = sample_client.post(
        "/api/charts/overview", json={"use_study_filters": True, "filters": filters}
    ).json()
    count = sample_client.post(
        "/api/suggestions/count",
        json={"session_id": "charts-session-1", "filters": filters, "exclude_studies": False},
    ).json()["count"]
    assert res["kpis"]["count"] == count
    assert res["scope_label"].startswith("Games matching")


def test_history_endpoint(
    online: Callable[[FakeSteam], tuple[TestClient, StudyService]],
) -> None:
    fake = FakeSteam([])
    client, service = online(fake)
    fake.apps = {a.appid: a for a in sample_apps(service)}
    appid = service.catalog().games[0].appid
    first = client.get(f"/api/charts/history/{appid}").json()
    assert first["enough_history"] is False and first["points"][0]["observed_at"] is None
    for _ in range(2):
        client.post("/api/data/jobs", json={"kind": "app", "appid": appid})
        wait_job(client)
    history = client.get(f"/api/charts/history/{appid}").json()
    assert history["enough_history"] is True and len(history["points"]) == 3
