"""Build the Windows desktop app into dist/SteamStudyTool/ (git-ignored).

Called by build.bat after the UI is built. Steps:
  1. Import the legacy HTML into a fresh seed catalog and verify the audited figures.
  2. Stage the seed catalog and the built UI as bundle resources.
  3. Run PyInstaller (one-folder, windowed) into build/, then update dist/SteamStudyTool/
     WITHOUT touching user files there (settings.json, data/, studiesJPG/, backups/).
  4. Smoke-test the built exe headless against a throwaway app folder.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from app.config import REFERENCE_HTML, REPO_ROOT
from app.db.connection import latest_schema_version, open_database
from app.db.queries import load_legacy_games
from app.importer import import_legacy_html

APP_NAME = "SteamStudyTool"
BUILD = REPO_ROOT / "build"
RESOURCES = BUILD / "desktop-resources"
PYI_DIST = BUILD / "pyinstaller-dist"
DIST = REPO_ROOT / "dist"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
# Files/folders in the output folder that belong to the user and must survive rebuilds.
USER_ENTRIES = {"settings.json", "data", "studiesJPG", "backups"}


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def build_seed_db() -> None:
    step("Importing legacy dataset into seed catalog")
    seed_dir = RESOURCES / "seed"
    shutil.rmtree(seed_dir, ignore_errors=True)
    seed_dir.mkdir(parents=True)
    seed = seed_dir / "catalog.sqlite3"
    conn = open_database(seed)
    result = import_legacy_html(conn, REFERENCE_HTML)
    games = load_legacy_games(conn)
    conn.close()
    qualified = sum(g.estimated_revenue >= 100_000 for g in games)
    if len(games) != 15_521 or qualified != 3_704:
        raise SystemExit(f"Seed verification failed: {len(games)} games, {qualified} >= $100K")
    # Fold the WAL into the main file and shrink it. (sqlite3's `with` only commits; it does not
    # close the connection, so close explicitly before touching the -wal/-shm files.)
    with closing(sqlite3.connect(seed, isolation_level=None)) as compact:
        compact.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        compact.execute("VACUUM")
        compact.execute("PRAGMA journal_mode = DELETE")  # single self-contained file
    for suffix in ("-wal", "-shm"):
        Path(f"{seed}{suffix}").unlink(missing_ok=True)
    # Deterministic version: only changes when the source data or schema changes, so a rebuild
    # does not make every PC re-copy the catalog.
    version = f"{result.source_sha256[:16]}-schema{latest_schema_version()}"
    (seed_dir / "catalog.version").write_text(version + "\n", encoding="utf-8")
    print(f"    {result.record_count} games, {qualified} qualified, catalog version {version}")


def stage_frontend() -> None:
    step("Staging built UI")
    if not (FRONTEND_DIST / "index.html").is_file():
        raise SystemExit("frontend/dist is missing - run `npm --prefix frontend run build` first")
    target = RESOURCES / "frontend_dist"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(FRONTEND_DIST, target, ignore=shutil.ignore_patterns("*.map"))


def run_pyinstaller() -> Path:
    step("Packaging with PyInstaller (one-folder, windowed)")
    import PyInstaller.__main__

    sep = os.pathsep
    migrations = REPO_ROOT / "backend" / "app" / "db" / "migrations"
    PyInstaller.__main__.run(
        [
            str(REPO_ROOT / "desktop" / "launcher.py"),
            "--name", APP_NAME,
            "--windowed",
            "--onedir",
            "--noconfirm",
            "--clean",
            "--log-level", "WARN",
            "--distpath", str(PYI_DIST),
            "--workpath", str(BUILD / "pyinstaller"),
            "--specpath", str(BUILD / "pyinstaller"),
            "--paths", str(REPO_ROOT / "backend"),
            "--add-data", f"{RESOURCES / 'seed'}{sep}seed",
            "--add-data", f"{RESOURCES / 'frontend_dist'}{sep}frontend_dist",
            "--add-data", f"{migrations}{sep}app/db/migrations",
            "--collect-submodules", "app",
            "--collect-submodules", "uvicorn",
            "--collect-all", "webview",
        ]
    )  # fmt: skip
    built = PYI_DIST / APP_NAME
    if not (built / f"{APP_NAME}.exe").is_file():
        raise SystemExit(f"PyInstaller did not produce {built}")
    return built


def install_into_dist(built: Path) -> Path:
    """Replace program files in dist/SteamStudyTool, keeping the user's data and settings."""
    step("Updating dist/SteamStudyTool (keeping settings.json, data, studiesJPG)")
    target = DIST / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    for entry in target.iterdir():
        if entry.name in USER_ENTRIES:
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except PermissionError as exc:
            raise SystemExit(
                f"Cannot replace {entry} - is SteamStudyTool still running? Close it and rebuild."
            ) from exc
    for entry in built.iterdir():
        destination = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination)
        else:
            shutil.copy2(entry, destination)
    kept = sorted(e.name for e in target.iterdir() if e.name in USER_ENTRIES)
    print(f"    kept: {', '.join(kept) if kept else '(nothing yet - created on first launch)'}")
    return target / f"{APP_NAME}.exe"


def smoke_test(exe: Path) -> None:
    step("Smoke-testing the built app (headless, throwaway app folder)")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "STEAM_STUDY_APP_DIR": tmp, "STEAM_STUDY_OFFLINE": "1"}
        proc = subprocess.run([str(exe), "--smoke-test"], env=env, timeout=180, check=False)
        logs = sorted((Path(tmp) / "data" / "logs").glob("launcher-*.log"))
        output = "\n".join(p.read_text(encoding="utf-8") for p in logs)
    if proc.returncode != 0 or "SMOKE OK" not in output:
        print(output)
        raise SystemExit(f"Smoke test FAILED (exit code {proc.returncode})")
    print("    " + next(line for line in output.splitlines() if "SMOKE OK" in line))


def write_readme(folder: Path) -> None:
    (folder / "README.txt").write_text(
        "Indie Case Study Suggester\n"
        "==========================\n\n"
        f"Double-click {APP_NAME}.exe to start. Close the window to quit.\n\n"
        "Everything is stored next to the exe, so this folder can live on a shared drive:\n"
        "  settings.json  - app settings (gear icon in the app); created on first launch\n"
        "  data\\          - game catalog, Studies (one file per game), caches, logs\n"
        "  studiesJPG\\    - JPG exports\n"
        "The data and export folders can be changed in Settings.\n\n"
        "Requires Windows 10/11 with the Microsoft Edge WebView2 runtime (preinstalled on\n"
        "current Windows); without it the app opens in your default browser instead.\n",
        encoding="utf-8",
    )


def folder_size_mb(folder: Path) -> float:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1_000_000


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("The desktop build targets Windows.")
    if not REFERENCE_HTML.is_file():
        raise SystemExit(
            "ERROR: reference/steam_game_suggester.html is missing. It is part of the repository:"
            " restore it with 'git checkout -- reference' and run build.bat again."
        )
    build_seed_db()
    stage_frontend()
    built = run_pyinstaller()
    exe = install_into_dist(built)
    write_readme(exe.parent)
    smoke_test(exe)
    step("Done")
    print(f"    {exe}")
    print(f"    program size: {folder_size_mb(built):.0f} MB")


if __name__ == "__main__":
    main()
