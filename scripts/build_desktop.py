"""Build the Windows desktop app into dist/SteamStudyTool/ (git-ignored).

Called by build.bat after the UI is built. Steps:
  1. Import the legacy HTML into a fresh seed database and verify the audited figures.
  2. Stage the seed DB and the built UI as bundle resources.
  3. Run PyInstaller (one-folder, windowed).
  4. Smoke-test the built exe headless against a throwaway data folder.
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
from app.db.connection import open_database
from app.db.queries import load_legacy_games
from app.importer import import_legacy_html

APP_NAME = "SteamStudyTool"
BUILD = REPO_ROOT / "build"
RESOURCES = BUILD / "desktop-resources"
DIST = REPO_ROOT / "dist"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def build_seed_db() -> None:
    step("Importing legacy dataset into seed database")
    seed_dir = RESOURCES / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    seed = seed_dir / "steam_study.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{seed}{suffix}").unlink(missing_ok=True)
    conn = open_database(seed)
    result = import_legacy_html(conn, REFERENCE_HTML)
    games = load_legacy_games(conn)
    conn.close()
    qualified = sum(g.estimated_revenue >= 100_000 for g in games)
    if len(games) != 15_521 or qualified != 3_704:
        raise SystemExit(f"Seed DB verification failed: {len(games)} games, {qualified} >= $100K")
    # Fold the WAL into the main file and shrink it. (sqlite3's `with` only commits; it does not
    # close the connection, so close explicitly before touching the -wal/-shm files.)
    with closing(sqlite3.connect(seed, isolation_level=None)) as compact:
        compact.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        compact.execute("VACUUM")
        compact.execute("PRAGMA journal_mode = DELETE")  # single self-contained file
    for suffix in ("-wal", "-shm"):
        Path(f"{seed}{suffix}").unlink(missing_ok=True)
    print(
        f"    {result.record_count} games, {qualified} qualified,"
        f" sha256 {result.source_sha256[:12]}"
    )


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
            "--distpath", str(DIST),
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
    exe = DIST / APP_NAME / f"{APP_NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"PyInstaller did not produce {exe}")
    return exe


def smoke_test(exe: Path) -> None:
    step("Smoke-testing the built app (headless)")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "STEAM_STUDY_HOME": tmp}
        proc = subprocess.run([str(exe), "--smoke-test"], env=env, timeout=120, check=False)
        log = Path(tmp) / "launcher.log"
        output = log.read_text(encoding="utf-8") if log.exists() else ""
    if proc.returncode != 0 or "SMOKE OK" not in output:
        print(output)
        raise SystemExit(f"Smoke test FAILED (exit code {proc.returncode})")
    print("    " + next(line for line in output.splitlines() if "SMOKE OK" in line))


def write_readme(folder: Path) -> None:
    (folder / "README.txt").write_text(
        "Indie Case Study Suggester\n"
        "==========================\n\n"
        f"Double-click {APP_NAME}.exe to start. Close the window to quit.\n\n"
        "Your data (study state, logs) is stored in %LOCALAPPDATA%\\SteamStudyTool and is kept\n"
        "when you rebuild or replace this folder. Delete that folder to start fresh.\n\n"
        "This folder can be copied anywhere (keep all files together). Requires Windows 10/11\n"
        "with the Microsoft Edge WebView2 runtime (preinstalled on current Windows); without it\n"
        "the app opens in your default browser instead.\n",
        encoding="utf-8",
    )


def folder_size_mb(folder: Path) -> float:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1_000_000


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("The desktop build targets Windows.")
    build_seed_db()
    stage_frontend()
    exe = run_pyinstaller()
    write_readme(exe.parent)
    smoke_test(exe)
    step("Done")
    print(f"    {exe}")
    print(f"    folder size: {folder_size_mb(exe.parent):.0f} MB")


if __name__ == "__main__":
    main()
