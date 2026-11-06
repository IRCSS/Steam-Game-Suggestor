from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import REFERENCE_HTML, Settings
from app.db.connection import open_database
from app.importer import LegacyRecord, extract_records, import_legacy_html
from app.main import create_app
from app.services import StudyService

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "legacy_sample.html"
LOCAL_ORIGIN = {"Origin": "http://127.0.0.1:5173"}


def make_settings(tmp_path: Path, threshold: int = 100_000) -> Settings:
    return Settings(
        db_path=tmp_path / "test.sqlite3", log_dir=None, qualification_min_revenue_usd=threshold
    )


@pytest.fixture
def sample_records() -> list[LegacyRecord]:
    return extract_records(SAMPLE_HTML.read_text(encoding="utf-8"))


@pytest.fixture
def sample_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = open_database(tmp_path / "sample.sqlite3")
    import_legacy_html(conn, SAMPLE_HTML)
    yield conn
    conn.close()


@pytest.fixture
def sample_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = make_settings(tmp_path)
    conn = open_database(settings.db_path)
    import_legacy_html(conn, SAMPLE_HTML)
    service = StudyService(settings, conn)
    with TestClient(create_app(settings, service)) as client:
        yield client
    service.close()


@pytest.fixture(scope="session")
def reference_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not REFERENCE_HTML.is_file():
        pytest.skip("reference/steam_game_suggester.html is missing")
    path = tmp_path_factory.mktemp("ref") / "reference.sqlite3"
    conn = open_database(path)
    import_legacy_html(conn, REFERENCE_HTML)
    conn.close()
    return path


@pytest.fixture(scope="session")
def reference_client(reference_db_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        db_path=reference_db_path, log_dir=None, qualification_min_revenue_usd=100_000
    )
    service = StudyService(settings)
    with TestClient(create_app(settings, service)) as client:
        yield client
    service.close()
