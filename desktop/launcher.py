"""Desktop entry point: double-click the exe -> local API starts -> app window opens.

* User data (SQLite DB, logs) lives in %LOCALAPPDATA%\\SteamStudyTool (override with
  STEAM_STUDY_HOME), never inside the build folder, so rebuilding never wipes study state.
* On first launch the pre-imported seed database shipped with the build is copied there.
* The API binds to 127.0.0.1 on a free port; closing the window stops the server.
* ``--smoke-test`` starts everything headless, checks /api/health and the UI, then exits
  (exit code 0 = OK). The build script uses it to verify each build.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

APP_NAME = "SteamStudyTool"
WINDOW_TITLE = "Indie Case Study Suggester"


def bundle_dir() -> Path:
    """Folder holding bundled resources (PyInstaller's _internal, or the repo in dev)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1] / "build" / "desktop-resources"


def user_home() -> Path:
    override = os.environ.get("STEAM_STUDY_HOME")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def prepare_environment(home: Path, resources: Path, log_file: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "steam_study.sqlite3"
    seed = resources / "seed" / "steam_study.sqlite3"
    if not db_path.exists():
        if not seed.is_file():
            raise FileNotFoundError(f"Seed database missing from the build: {seed}")
        shutil.copy2(seed, db_path)
    os.environ["STEAM_STUDY_DB"] = str(db_path)
    os.environ["STEAM_STUDY_LOG_DIR"] = str(home / "logs")
    os.environ["STEAM_STUDY_FRONTEND_DIST"] = str(resources / "frontend_dist")
    # A windowed exe has no console: send stray prints/tracebacks to a log file.
    if sys.stdout is None or sys.stderr is None:
        stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_up(url: str, timeout: float = 30.0) -> None:
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


def start_server(port: int):  # type: ignore[no-untyped-def]
    import uvicorn

    from app.main import create_app  # imported after env vars are set

    config = uvicorn.Config(
        create_app(), host="127.0.0.1", port=port, log_config=None, access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="api-server", daemon=True)
    thread.start()
    return server, thread


def smoke_test(base: str) -> int:
    """Headless self-check of the packaged app: API up, data present, UI and its JS servable."""
    import re

    with urllib.request.urlopen(f"{base}/api/health", timeout=5) as r:
        health = r.read().decode()
    with urllib.request.urlopen(f"{base}/", timeout=5) as r:
        page = r.read().decode()
    script = re.search(r'src="(/assets/[^"]+\.js)"', page)
    js_type = ""
    if script:
        with urllib.request.urlopen(f"{base}{script.group(1)}", timeout=5) as r:
            js_type = r.headers.get("Content-Type", "")
    checks = {
        "api": '"status":"ok"' in health and '"games":0' not in health,
        "ui": "<title>Indie Case Study Suggester</title>" in page,
        "js_mime": "javascript" in js_type,  # text/plain => blank window in WebView2
    }
    ok = all(checks.values())
    print(f"SMOKE {'OK' if ok else 'FAILED'} {checks} js={js_type!r} health={health}", flush=True)
    return 0 if ok else 1


def show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, 0x10)  # type: ignore[attr-defined]
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    home = user_home()
    home.mkdir(parents=True, exist_ok=True)
    log_file = home / "launcher.log"
    try:
        prepare_environment(home, bundle_dir(), log_file)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        server, thread = start_server(port)
        wait_until_up(f"{base}/api/health")

        if "--smoke-test" in sys.argv:
            code = smoke_test(base)
            server.should_exit = True
            thread.join(timeout=10)
            return code

        try:
            import webview

            webview.create_window(WINDOW_TITLE, base, width=1440, height=960, min_size=(420, 600))
            webview.start(private_mode=False, storage_path=str(home / "webview"))
        except Exception:
            # No WebView2 runtime (or other failure): use the default browser instead and keep
            # serving until the process is ended.
            traceback.print_exc()
            import webbrowser

            webbrowser.open(base)
            show_error(
                "Opened the app in your web browser because the built-in window could not "
                "start.\n\nClose this message to quit the app."
            )
        server.should_exit = True
        thread.join(timeout=10)
        return 0
    except Exception:
        details = traceback.format_exc()
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(details)
        show_error(f"{WINDOW_TITLE} could not start.\n\nDetails were written to:\n{log_file}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
