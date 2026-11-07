"""Dataset export (Settings -> Export dataset): one zip of CSV + JSON tables."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.observations import ReviewsObservation
from app.domain.research import Estimate, Insight, ResearchFindings
from app.services import StudyService
from app.storage.research import ResearchRun, ResearchStore
from app.storage.studies import StudyStore

TABLES = ("games", "studies", "research", "review_history")


def export(client: TestClient) -> zipfile.ZipFile:
    res = client.post("/api/exports/dataset")
    assert res.status_code == 200, res.text
    path = Path(res.json()["path"])
    assert path.suffix == ".zip" and path.name.startswith("steam-study-dataset-")
    return zipfile.ZipFile(path)


def read_csv(archive: zipfile.ZipFile, table: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(archive.read(f"csv/{table}.csv").decode("utf-8"))))


def read_json(archive: zipfile.ZipFile, name: str) -> Any:
    return json.loads(archive.read(f"json/{name}.json"))


def test_export_contains_every_table_as_csv_and_json(
    sample_client: TestClient, sample_settings: Settings
) -> None:
    service: StudyService = sample_client.app.state.service  # type: ignore[attr-defined]
    first = service.catalog().games[0].appid
    StudyStore(sample_settings.studies_dir).add(first, "Studied game")
    ResearchStore(sample_settings.research_dir).add(
        ResearchRun(
            kind="budget", appid=first, name="Studied game", created_at="2026-11-07T10:00:00+00:00",
            created_by="pc1",
            findings=ResearchFindings(
                studio="Studio", team_size=Estimate(low=2, high=4, best=3, confidence="medium"),
                development_months=Estimate(best=24, confidence="low"),
            ),
        )
    )  # fmt: skip
    ResearchStore(sample_settings.research_dir).add(
        ResearchRun(
            kind="reviews", appid=first, name="Studied game",
            created_at="2026-11-07T11:00:00+00:00", created_by="pc1",
            findings=ResearchFindings(
                why_it_worked=[Insight(point='Fun, "tight" loop', evidence="many")],
            ),
        )
    )  # fmt: skip
    service.observations.append(
        ReviewsObservation(first, "2026-11-01T00:00:00+00:00", 500, 450, 50)
    )

    archive = export(sample_client)
    names = set(archive.namelist())
    assert {"README.md", "dataset.json", "json/research-details.json"} <= names
    for table in TABLES:
        assert f"csv/{table}.csv" in names and f"json/{table}.json" in names
        assert len(read_csv(archive, table)) == len(read_json(archive, table))
        assert f"## {table}" in archive.read("README.md").decode("utf-8")

    manifest = json.loads(archive.read("dataset.json"))
    assert manifest["tables"]["studies"] == 1 and manifest["tables"]["research"] == 1
    assert manifest["cost_model"]["salary_per_person_year"] == 50_000

    rows = {int(r["appid"]): r for r in read_csv(archive, "games")}
    assert len(rows) == manifest["tables"]["games"] > 1
    row = rows[first]
    assert row["in_studies"] == "true" and row["total_reviews"] == "500"  # newest Steam data
    assert isinstance(json.loads(row["tags"]), list)  # list cells are JSON arrays
    assert all(r["english"] == "" for r in rows.values())  # unknown stays empty, not "false"
    assert read_json(archive, "games")[0]["tags"] == json.loads(
        read_csv(archive, "games")[0]["tags"]
    )

    (research,) = read_csv(archive, "research")
    assert research["studio"] == "Studio" and research["team_size_best"] == "3.0"
    assert (
        research["development_months_low"] == "" and research["development_months_best"] == "24.0"
    )
    assert float(research["cost_best"]) == 3 * 2 * 50_000 and research["cost_currency"] == "EUR"
    assert json.loads(research["why_it_worked"]) == ['Fun, "tight" loop']  # quoting survives
    assert research["reviews_researched_at"].startswith("2026-11-07T11")
    (detail,) = read_json(archive, "research-details")
    assert detail["budget"]["kind"] == "budget" and detail["reviews"]["kind"] == "reviews"
    assert detail["economics"]["cost"]["best"] == 300_000

    history = read_csv(archive, "review_history")
    assert [h["total_reviews"] for h in history] == ["500"]


def test_export_with_no_user_data(sample_client: TestClient) -> None:
    archive = export(sample_client)
    assert read_csv(archive, "studies") == [] and read_json(archive, "research") == []
    header = archive.read("csv/research.csv").decode("utf-8").splitlines()[0]
    assert header.startswith("appid,name,studio,team_size_low")  # header even when empty
