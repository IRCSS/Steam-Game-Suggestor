"""Zip the built desktop app for a GitHub release - program files only.

Includes SteamStudyTool.exe, _internal/ (app + seed game catalog) and README.txt from
dist/SteamStudyTool. Never includes per-user state that lives next to the exe after use
(settings.json - may contain API keys -, data/, studiesJPG/, backups/).

Usage: build.bat first, then:  uv run python scripts/package_release.py
Output: dist/SteamStudyTool-<version>-windows.zip
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

from app.config import APP_VERSION, REPO_ROOT

APP = "SteamStudyTool"
SOURCE = REPO_ROOT / "dist" / APP
RELEASE_ITEMS = (f"{APP}.exe", "_internal", "README.txt")
USER_ITEMS = {"settings.json", "data", "studiesJPG", "backups"}


def main() -> int:
    if not (SOURCE / f"{APP}.exe").is_file():
        print(f"ERROR: {SOURCE / (APP + '.exe')} not found - run build.bat first.", file=sys.stderr)
        return 1
    unexpected = sorted(
        p.name
        for p in SOURCE.iterdir()
        if p.name not in RELEASE_ITEMS and p.name not in USER_ITEMS
        and not p.name.startswith("settings.invalid-")
    )  # fmt: skip
    if unexpected:
        print(
            f"ERROR: unexpected files in {SOURCE}: {unexpected}. Check, then retry.",
            file=sys.stderr,
        )
        return 1
    target = REPO_ROOT / "dist" / f"{APP}-{APP_VERSION}-windows.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in RELEASE_ITEMS:
            path = SOURCE / item
            files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
            for file in files:
                archive.write(file, Path(APP) / file.relative_to(SOURCE))
                count += 1
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    leaked = [n for n in names if n.split("/")[1] in USER_ITEMS or "settings" in n.split("/")[1]]
    if leaked:
        target.unlink()
        print(f"ERROR: user files ended up in the zip: {leaked[:5]}", file=sys.stderr)
        return 1
    size_mb = target.stat().st_size / 1_000_000
    print(f"{target} ({count} files, {size_mb:.0f} MB) - program files only, no settings/data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
