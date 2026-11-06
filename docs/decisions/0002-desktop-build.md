# ADR 0002: Desktop build pulled forward for user testing

Status: accepted. Date: 2026-11-06.

## Context
The user wants to test the app as a double-clickable program (no terminal, no manual server) and
asked for a one-step build script. Plan Phase 6 already specifies pywebview + PyInstaller as a
one-folder build, so the packaging part is pulled forward. Backup/restore hardening, the
single-instance guard and installers stay in Phase 6.

## Decision
- `build.bat` -> `uv sync --group desktop`, `npm ci` + UI build, then `scripts/build_desktop.py`:
  1. builds a seed SQLite DB from the reference HTML and verifies it (15,521 games, 3,704 qualified);
  2. stages the seed DB and the built UI (without source maps);
  3. runs PyInstaller `--onedir --windowed` -> `dist/SteamStudyTool/`;
  4. runs `SteamStudyTool.exe --smoke-test` against a throwaway data folder. This checks that
     the API is up, data is present, the UI is served, and the JS is served with a JavaScript
     MIME type.
- `desktop/launcher.py`:
  - user data goes in `%LOCALAPPDATA%\SteamStudyTool` (`STEAM_STUDY_HOME` overrides it), and the
    seed DB is copied there on first run only;
  - uvicorn runs in a background thread on a free 127.0.0.1 port;
  - a pywebview window opens; closing it stops the server;
  - if WebView2 fails, the app falls back to the default browser;
  - startup errors are written to `launcher.log` and shown in a message box.
- Desktop dependencies live in a separate uv dependency group (`desktop`), so the web and dev
  setup stays unchanged.

## Consequences
- Rebuilds never touch user data. Future schema changes reach existing user databases through
  the normal migrations, which run at startup.
- The build is about 58 MB (Python runtime, WebView2 bindings, seed DB). It is Windows-only.
- The exe is unsigned, so Windows SmartScreen may warn on other PCs ("More info" -> "Run anyway").
- No single-instance guard yet. Two windows can run against the same DB, which is safe with WAL.

## Bug found while doing this
Python's `mimetypes` reads the Windows registry, which on this machine maps `.js` to `text/plain`.
FastAPI then served the UI bundle as text/plain, and WebView2 refused to run it (blank window).
This also affected `npm run start`. The e2e tests missed it because they use Vite's dev server.
The fix is `register_web_mimetypes()` in `app/main.py`. A regression test
(`test_static_ui.py`) fails without the fix, and the build smoke test checks the served type.
