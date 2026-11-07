from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import CATALOG_FILE_NAME, REFERENCE_HTML, Settings
from app.db.connection import open_database
from app.importer import LegacyRecord, extract_records, import_legacy_html
from app.main import create_app
from app.services import StudyService

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "legacy_sample.html"
LOCAL_ORIGIN = {"Origin": "http://127.0.0.1:5173"}


def make_settings(
    tmp_path: Path, threshold: int = 100_000, offline: bool = True, rpm: int = 120
) -> Settings:
    """Isolated app folder layout: <tmp>/settings.json, <tmp>/data/..., <tmp>/studiesJPG."""
    return Settings(
        app_dir=tmp_path,
        data_dir=tmp_path / "data",
        export_dir=tmp_path / "studiesJPG",
        qualification_min_revenue_usd=threshold,
        offline=offline,
        steam_requests_per_minute=rpm,
    )


def import_sample(settings: Settings) -> None:
    conn = open_database(settings.catalog_path)
    import_legacy_html(conn, SAMPLE_HTML)
    conn.close()


@pytest.fixture
def sample_records() -> list[LegacyRecord]:
    return extract_records(SAMPLE_HTML.read_text(encoding="utf-8"))


@pytest.fixture
def sample_db(tmp_path: Path) -> Iterator[object]:
    conn = open_database(tmp_path / "sample.sqlite3")
    import_legacy_html(conn, SAMPLE_HTML)
    yield conn
    conn.close()


@pytest.fixture
def sample_settings(tmp_path: Path) -> Settings:
    settings = make_settings(tmp_path)
    import_sample(settings)
    return settings


@pytest.fixture
def sample_client(sample_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(sample_settings)) as client:
        yield client


HttpHandler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def online_client_factory(
    tmp_path: Path,
) -> Iterator[Callable[[HttpHandler], tuple[TestClient, StudyService]]]:
    """App with a mocked Steam (httpx.MockTransport) - never touches the network."""
    clients: list[TestClient] = []

    def build(handler: HttpHandler) -> tuple[TestClient, StudyService]:
        settings = make_settings(tmp_path, offline=False)
        import_sample(settings)
        service = StudyService(
            settings, http_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler))
        )
        client = TestClient(create_app(settings, service))
        client.__enter__()
        clients.append(client)
        return client, service

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture(scope="session")
def reference_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    assert REFERENCE_HTML.is_file(), "reference/steam_game_suggester.html is missing"
    path = tmp_path_factory.mktemp("ref") / "data" / CATALOG_FILE_NAME
    conn = open_database(path)
    import_legacy_html(conn, REFERENCE_HTML)
    conn.close()
    return path


@pytest.fixture(scope="session")
def reference_client(reference_db_path: Path) -> Iterator[TestClient]:
    app_dir = reference_db_path.parent.parent
    settings = Settings(
        app_dir=app_dir, data_dir=app_dir / "data", export_dir=app_dir / "studiesJPG", offline=True
    )
    with TestClient(create_app(settings)) as client:
        yield client
