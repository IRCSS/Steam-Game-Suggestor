"""Back up user state: settings.json + the data folder's studies and caches (zip).

The game catalog is excluded (it is rebuilt from the reference file by every build).

Usage: uv run python scripts/backup_db.py [--out-dir <app dir>/backups]
"""

from __future__ import annotations

import argparse
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.config import CATALOG_FILE_NAME, load_settings, settings_path


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=settings.app_dir / "backups")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = args.out_dir / f"steam-study-backup-{stamp}.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        if settings_path(settings.app_dir).is_file():
            archive.write(settings_path(settings.app_dir), "settings.json")
            count += 1
        for path in sorted(settings.data_dir.rglob("*")):
            if path.is_file() and not path.name.startswith(CATALOG_FILE_NAME):
                archive.write(path, Path("data") / path.relative_to(settings.data_dir))
                count += 1
    print(f"backup written to {target} ({count} files)")


if __name__ == "__main__":
    main()
