# Claude Code project instructions

- Read STEAM_STUDY_TOOL_IMPLEMENTATION_PLAN.md and the latest `docs/phase-reports/` report first.
- Keep `reference/steam_game_suggester.html` unchanged; it is the baseline for both data and visual behavior (SHA-256 checked in tests).
- Work on one phase or vertical slice at a time. Do not opportunistically rewrite unrelated areas.
- Database/AppID and source schemas are stable contracts. Make schema changes only through numbered SQL migrations in `backend/app/db/migrations/`.
- Business logic belongs in Python domain modules (`backend/app/domain/`), not in route functions or React components.
- Never bundle the original 11 MB data into the shipped frontend.
- Never treat estimates as actual revenue, sales, historical prices, team sizes or budgets.
- Never put provider API keys in the browser, Git, prompts, fixtures or logs.
- No real Steam/API/model calls in automated tests; use recorded, sanitized fixtures and mocks. E2E blocks all non-localhost requests.
- All external operations must be bounded, rate-limited, resumable and user-triggered unless explicitly approved otherwise.
- Always add or update tests for new behavior and bug fixes.
- After any API schema change, run `npm run gen-api` (the contract test fails otherwise).
- Before completion, run `npm run check` and `npm run test-e2e`. Fix failures and provide artifacts and repro steps.
- Keep user notes, study status and human-verified research immutable across refresh/import jobs.
- Report changed files, passed/failed checks, known limitations and next actions after each phase.

## Desktop build

- `build.bat` (repo root) produces `dist/SteamStudyTool/SteamStudyTool.exe` (git-ignored). It must self-test (`--smoke-test`) green; see `docs/decisions/0002-desktop-build.md`.
- User data lives in `%LOCALAPPDATA%\SteamStudyTool`; never store state in the build folder.
- Anything the packaged app needs at runtime (SQL migrations, UI, seed DB) must be added in `scripts/build_desktop.py`.

## Environment notes (Windows dev machine)

- Shell PATH may lack the new tools in an old session. uv is installed via winget; Python 3.12 is at `%LOCALAPPDATA%\Programs\Python\Python312`; Node is at `C:\Program Files\nodejs`.
- The legacy CSS hides the real checkboxes in `label.switch` / `label.year-option`, so Playwright toggles them by clicking the label (`setToggle` in `e2e/fixtures.ts`).
