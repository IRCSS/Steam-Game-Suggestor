"""Desktop entry point: double-click the exe -> local API starts -> app window opens.

Everything lives next to the exe (so the folder can sit on a shared drive such as G:):
  settings.json   created with defaults on first launch; edited from the gear icon
  data\\           default data folder (catalog, studies, caches, logs) - configurable
  studiesJPG\\     default JPG export folder - configurable
Nothing is written to %LOCALAPPDATA%: the embedded browser runs in private mode.

* The game catalog ships inside the build as a seed. It is copied into the data folder when
  missing, and replaced when a newer build ships a different catalog (it holds no user data).
* The API binds to 127.0.0.1 on a free port; closing the window stops the server.
* ``--smoke-test`` starts everything headless, checks the API/UI, then exits (0 = OK).
* STEAM_STUDY_APP_DIR overrides the app folder (used by the build's smoke test).
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any

WINDOW_TITLE = "Indie Case Study Suggester"
SEED_DB = "catalog.sqlite3"
SEED_VERSION = "catalog.version"


def bundle_dir() -> Path:
    """Folder holding bundled resources (PyInstaller's _internal, or build staging in dev)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1] / "build" / "desktop-resources"


def app_dir() -> Path:
    override = os.environ.get("STEAM_STUDY_APP_DIR")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1] / ".local"


def install_catalog(data_dir: Path, resources: Path, log: list[str]) -> None:
    """Copy the bundled catalog into the data folder if missing or from an older build."""
    seed = resources / "seed" / SEED_DB
    seed_version_file = resources / "seed" / SEED_VERSION
    target = data_dir / SEED_DB
    version_file = data_dir / SEED_VERSION
    if not seed.is_file():
        if not target.is_file():
            raise FileNotFoundError(f"Seed catalog missing from the build: {seed}")
        return
    seed_version = seed_version_file.read_text(encoding="utf-8").strip()
    current = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""
    if target.is_file() and current == seed_version:
        return
    tmp = data_dir / f".{SEED_DB}.{os.getpid()}.tmp"
    try:
        shutil.copy2(seed, tmp)
        os.replace(tmp, target)
        version_file.write_text(seed_version + "\n", encoding="utf-8")
        log.append(f"catalog installed ({seed_version})")
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        if not target.is_file():
            raise
        # Another PC may have it open; keep using the existing copy.
        log.append(f"catalog not replaced ({exc}); using existing copy")


def prepare(app: Path, resources: Path) -> tuple[Any, Path, list[str]]:
    """Create/read settings.json, make sure the data folder and catalog exist."""
    os.environ["STEAM_STUDY_APP_DIR"] = str(app)
    os.environ["STEAM_STUDY_FRONTEND_DIST"] = str(resources / "frontend_dist")
    from app.config import load_settings  # after env vars are set

    settings = load_settings(app)
    notes: list[str] = []
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"The data folder is not available:\n{settings.data_dir}\n\n{exc}\n\n"
            f"If it is on a network or cloud drive, make sure the drive is connected, or change "
            f'"data_dir" in:\n{app / "settings.json"}'
        ) from exc
    install_catalog(settings.data_dir, resources, notes)
    return settings, settings.data_dir / "logs", notes


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_up(url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # server still starting
            last_error = exc
        time.sleep(0.15)
    raise TimeoutError(f"Local server did not start: {last_error}")


def start_server(settings: Any, port: int) -> tuple[Any, threading.Thread]:
    import uvicorn

    from app.main import create_app

    config = uvicorn.Config(
        create_app(settings), host="127.0.0.1", port=port, log_config=None, access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="api-server", daemon=True)
    thread.start()
    return server, thread


def smoke_test(base: str, app: Path) -> int:
    """Headless self-check of the packaged app: API, data, UI, JS MIME type, file layout."""
    with urllib.request.urlopen(f"{base}/api/health", timeout=10) as r:
        health = r.read().decode()
    with urllib.request.urlopen(f"{base}/", timeout=10) as r:
        page = r.read().decode()
    script = re.search(r'src="(/assets/[^"]+\.js)"', page)
    js_type = ""
    if script:
        with urllib.request.urlopen(f"{base}{script.group(1)}", timeout=10) as r:
            js_type = r.headers.get("Content-Type", "")
    with urllib.request.urlopen(f"{base}/api/studies", timeout=10) as r:
        studies = r.read().decode()
    checks = {
        "api": '"status":"ok"' in health and '"games":0' not in health,
        "ui": "<title>Indie Case Study Suggester</title>" in page,
        "js_mime": "javascript" in js_type,  # text/plain => blank window in WebView2
        "settings_json": (app / "settings.json").is_file(),
        "catalog_next_to_exe": (app / "data" / SEED_DB).is_file(),
        "studies_api": '"items"' in studies,
    }
    ok = all(checks.values())
    print(f"SMOKE {'OK' if ok else 'FAILED'} {checks} js={js_type!r} health={health}", flush=True)
    return 0 if ok else 1


def show_message(message: str, error: bool = True) -> None:
    try:
        import ctypes

        flags = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, flags)  # type: ignore[attr-defined]
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    app = app_dir()
    log_file = Path(tempfile.gettempdir()) / "SteamStudyTool-launcher.log"
    try:
        settings, log_dir, notes = prepare(app, bundle_dir())
        log_dir.mkdir(parents=True, exist_ok=True)
        from app.storage.files import machine_id

        log_file = log_dir / f"launcher-{machine_id()}.log"
        if sys.stdout is None or sys.stderr is None:  # windowed exe: no console
            stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
            sys.stdout = sys.stdout or stream
            sys.stderr = sys.stderr or stream
        for note in notes:
            print(note, flush=True)

        port = free_port()
        base = f"http://127.0.0.1:{port}"
        server, thread = start_server(settings, port)
        wait_until_up(f"{base}/api/health")

        if "--smoke-test" in sys.argv:
            code = smoke_test(base, app)
            server.should_exit = True
            thread.join(timeout=10)
            return code

        try:
            import webview

            webview.create_window(WINDOW_TITLE, base, width=1440, height=960, min_size=(420, 600))
            webview.start(private_mode=True)  # no browser profile on disk (no %LOCALAPPDATA%)
        except Exception:
            traceback.print_exc()
            import webbrowser

            webbrowser.open(base)
            show_message(
                "Opened the app in your web browser because the built-in window could not "
                "start.\n\nClose this message to quit the app.",
                error=False,
            )
        server.should_exit = True
        thread.join(timeout=10)
        return 0
    except Exception as exc:
        details = traceback.format_exc()
        try:
            with open(log_file, "a", encoding="utf-8") as handle:
                handle.write(details)
        except OSError:
            pass
        message = (
            str(exc)
            if isinstance(exc, RuntimeError)
            else (f"{WINDOW_TITLE} could not start:\n{exc}\n\nDetails: {log_file}")
        )
        print(message, file=sys.stderr)
        if "--smoke-test" not in sys.argv:  # never block an unattended build with a dialog
            show_message(message)
        return 1


if __name__ == "__main__":
    sys.exit(main())
