from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from tests.conftest import LOCAL_ORIGIN

SESSION = "test-session-0001"


def defaults(client: TestClient) -> dict[str, Any]:
    return client.get("/api/meta").json()["default_filters"]


def body(client: TestClient, session: str = SESSION, **overrides: Any) -> dict[str, Any]:
    filters = {**defaults(client), **overrides.pop("filters", {})}
    return {"session_id": session, "filters": filters, **overrides}


def test_health_and_meta(sample_client: TestClient) -> None:
    health = sample_client.get("/api/health").json()
    assert health["status"] == "ok" and health["schema_version"] >= 1 and health["games"] == 55
    meta = sample_client.get("/api/meta").json()
    assert meta["years"] == [2022, 2023, 2024, 2025]
    assert meta["tags"] == sorted(meta["tags"])
    assert meta["dataset"]["qualification_threshold_usd"] == 100_000
    assert meta["dataset"]["revenue_model"] == "legacy_reviews_x45_price"
    d = meta["default_filters"]
    assert (d["min_revenue"], d["max_revenue"], d["min_review_score"]) == (150_000, 800_000, 50)
    assert d["max_reviews"] is None


def test_game_report_shape_and_404(sample_client: TestClient) -> None:
    item = sample_client.get("/api/games", params={"q": "a", "limit": 1}).json()["items"][0]
    report = sample_client.get(f"/api/games/{item['appid']}").json()
    assert report["price"]["context"] == "legacy_price_context_unknown"
    assert report["reviews"]["observed_at"] is None
    assert report["estimated_revenue"]["model"] == "legacy_reviews_x45_price"
    assert report["estimated_revenue"]["amount_minor"] == item["estimated_revenue_usd"] * 100
    assert report["rank"]["population"].startswith("local_catalog_games_")
    # The 55-game fixture is a subset, so ranks recomputed within it differ from the legacy
    # ones - and the label must then say so. (Full catalog: identical, see reference test.)
    assert report["rank"]["legacy_rank"] is not None
    expected = (
        "legacy dataset"
        if report["rank"]["rank"] == report["rank"]["legacy_rank"]
        else "local catalog"
    )
    assert report["rank"]["scope_label"].startswith(expected)
    assert report["provenance"]["data_source"] == "legacy_import"
    assert report["steam_url"] == f"https://store.steampowered.com/app/{item['appid']}"
    assert sample_client.get("/api/games/1").status_code == 404


def test_lookup_bypasses_filters_and_qualification(sample_client: TestClient) -> None:
    # A game far below the $100K floor and outside default filters must still load.
    low = min(
        (sample_client.get(f"/api/games/{s['appid']}").json() for s in _all(sample_client)),
        key=lambda r: int(r["estimated_revenue"]["amount_minor"]),  # pyright: ignore[reportUnknownLambdaType]
    )
    assert low["qualification"]["qualified"] is False
    resolved = sample_client.get("/api/games/resolve", params={"q": str(low["appid"])}).json()
    assert resolved["appid"] == low["appid"]
    by_name = sample_client.get("/api/games/resolve", params={"q": low["name"].upper()}).json()
    assert by_name["name"].lower() == low["name"].lower()
    assert sample_client.get("/api/games/resolve", params={"q": "zzzz-nope"}).status_code == 404


def _all(client: TestClient) -> list[dict[str, Any]]:
    # Every fixture name contains a vowel or digit; union of a few queries covers the sample.
    seen: dict[int, dict[str, Any]] = {}
    for q in "aeiouy0123456789":
        for item in client.get("/api/games", params={"q": q, "limit": 100}).json()["items"]:
            seen[item["appid"]] = item
    return list(seen.values())


def test_suggest_avoids_repeats_until_exhausted(sample_client: TestClient) -> None:
    payload = body(sample_client)
    total = sample_client.post("/api/suggestions/count", json=payload).json()
    assert total["count"] > 1 and total["count"] == total["count_ignoring_history"]
    shown: list[int] = []
    for i in range(total["count"]):
        res = sample_client.post("/api/suggestions", json={**payload, "seed": i}).json()
        assert res["status"] == "ok" and not res["repeat_history_reset"]
        assert res["game"]["appid"] not in shown
        shown.append(res["game"]["appid"])
    count = sample_client.post("/api/suggestions/count", json=payload).json()
    assert count == {"count": 0, "count_ignoring_history": total["count"], "all_seen": True}
    res = sample_client.post("/api/suggestions", json={**payload, "seed": 99}).json()
    assert res["repeat_history_reset"] is True
    # After the reset only the newly shown game counts as seen; history list is preserved.
    count = sample_client.post("/api/suggestions/count", json=payload).json()
    assert count["count"] == total["count"] - 1
    history = sample_client.get(f"/api/sessions/{SESSION}/history").json()["items"]
    assert len(history) == min(12, total["count"])
    assert history[0]["appid"] == res["game"]["appid"]


def test_seeded_suggestions_are_deterministic(sample_client: TestClient) -> None:
    a = sample_client.post(
        "/api/suggestions", json={**body(sample_client, "seed-a-0001"), "seed": 5}
    )
    b = sample_client.post(
        "/api/suggestions", json={**body(sample_client, "seed-b-0001"), "seed": 5}
    )
    assert a.json()["game"]["appid"] == b.json()["game"]["appid"]


def test_history_is_last_12_distinct_and_clear(sample_client: TestClient) -> None:
    session = "hist-session-01"
    items = _all(sample_client)
    for item in items[:14]:
        r = sample_client.post(f"/api/sessions/{session}/views", json={"appid": item["appid"]})
        assert r.status_code == 200
    # Re-viewing an older game moves it to the front without duplicating it.
    sample_client.post(f"/api/sessions/{session}/views", json={"appid": items[5]["appid"]})
    history = sample_client.get(f"/api/sessions/{session}/history").json()["items"]
    assert len(history) == 12
    assert history[0]["appid"] == items[5]["appid"]
    assert len({h["appid"] for h in history}) == 12
    assert sample_client.post(f"/api/sessions/{session}/clear").json() == {"items": []}
    assert sample_client.get(f"/api/sessions/{session}/history").json()["items"] == []


def test_manual_lookup_counts_as_seen(sample_client: TestClient) -> None:
    session = "manual-seen-01"
    payload = body(sample_client, session)
    first = sample_client.post("/api/suggestions", json={**payload, "seed": 1}).json()["game"]
    before = sample_client.post("/api/suggestions/count", json=payload).json()["count"]
    other = next(
        s["appid"]
        for s in _all(sample_client)
        if s["appid"] != first["appid"] and 150_000 <= s["estimated_revenue_usd"] <= 800_000
    )
    sample_client.post(f"/api/sessions/{session}/views", json={"appid": other})
    after = sample_client.post("/api/suggestions/count", json=payload).json()["count"]
    assert after in (before, before - 1)  # -1 when the looked-up game is in the filtered pool


def test_qualification_gate(sample_client: TestClient) -> None:
    wide = {"min_revenue": None, "max_revenue": None, "min_review_score": None}
    gated = sample_client.post("/api/suggestions/count", json=body(sample_client, filters=wide))
    open_ = sample_client.post(
        "/api/suggestions/count",
        json=body(sample_client, filters=wide, include_below_threshold=True),
    )
    assert open_.json()["count"] > gated.json()["count"] > 0


def test_no_matches_response(sample_client: TestClient) -> None:
    res = sample_client.post(
        "/api/suggestions", json=body(sample_client, filters={"include_tags": "zz-not-a-tag"})
    ).json()
    assert res == {
        "status": "no_matches",
        "game": None,
        "repeat_history_reset": False,
        "candidate_count": 0,
    }


@pytest.mark.parametrize("bad", ["short", "has space here", "x" * 65, "semi;colon-123"])
def test_session_id_validation(sample_client: TestClient, bad: str) -> None:
    assert sample_client.post("/api/suggestions", json=body(sample_client, bad)).status_code == 422


def test_cross_origin_writes_blocked(sample_client: TestClient) -> None:
    r = sample_client.post(
        "/api/suggestions", json=body(sample_client), headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403
    ok = sample_client.post("/api/suggestions", json=body(sample_client), headers=LOCAL_ORIGIN)
    assert ok.status_code == 200
    assert "x-request-id" in ok.headers


def test_openapi_contract_is_committed(sample_client: TestClient) -> None:
    """frontend/openapi.json must match the live schema; run `npm run gen-api` after changes."""
    committed = json.loads((REPO_ROOT / "frontend" / "openapi.json").read_text(encoding="utf-8"))
    assert sample_client.get("/openapi.json").json() == committed


@pytest.mark.reference
def test_reference_default_counts(reference_client: TestClient) -> None:
    payload = body(reference_client, "reference-01")
    gated = reference_client.post("/api/suggestions/count", json=payload).json()
    ungated = reference_client.post(
        "/api/suggestions/count", json={**payload, "include_below_threshold": True}
    ).json()
    # Default $150K floor sits above the $100K gate, so the gate changes nothing by default.
    assert gated == ungated
    assert gated["count"] == LEGACY_DEFAULT_MATCH_COUNT
    meta = reference_client.get("/api/meta").json()
    assert meta["dataset"]["total_games"] == 15_521
    assert meta["dataset"]["qualified_games"] == 3_704
    assert len(meta["tags"]) == 443
    assert meta["default_filters"]["max_rank"] == 4982


@pytest.mark.reference
def test_reference_lookup_vampire(reference_client: TestClient) -> None:
    items = reference_client.get("/api/games", params={"q": "vampire"}).json()["items"]
    assert len(items) == 12
    assert items[0]["name"].lower().startswith("vampire")
    exact = reference_client.get("/api/games", params={"q": "1794680"}).json()["items"]
    assert [i["name"] for i in exact] == ["Vampire Survivors"]


# Value observed in the legacy HTML (Playwright parity test e2e/parity.spec.ts checks it live).
LEGACY_DEFAULT_MATCH_COUNT = 1743
