"""Write the FastAPI OpenAPI schema to frontend/openapi.json (source for generated TS types)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.config import REPO_ROOT, Settings
from app.main import create_app
from app.services import StudyService

OUT = REPO_ROOT / "frontend" / "openapi.json"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            app_dir=Path(tmp), data_dir=Path(tmp) / "data", export_dir=Path(tmp) / "x"
        )
        service = StudyService(settings)
        schema = create_app(settings, service).openapi()
        service.close()
    OUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
