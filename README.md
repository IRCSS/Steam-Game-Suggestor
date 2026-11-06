# Steam Study Tool

Local-first tool that suggests Steam games to study, built from the legacy
`reference/steam_game_suggester.html`. It is a React UI backed by a Python (FastAPI) service and a
local SQLite database.

**Status:** Phase 0 + Phase 1 (offline suggestion app at legacy parity). See
[`STEAM_STUDY_TOOL_IMPLEMENTATION_PLAN.md`](STEAM_STUDY_TOOL_IMPLEMENTATION_PLAN.md) and
[`docs/phase-reports/phase-1.md`](docs/phase-reports/phase-1.md).

Everything runs offline. No Steam API key or AI key is needed, and nothing calls external services
(Steam artwork is only loaded by your browser, from Steam's CDN).

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm

On Windows: `winget install Python.Python.3.12 astral-sh.uv OpenJS.NodeJS.LTS`

## Desktop app (the build to test)

Double-click **`build.bat`** in the repo root. It installs dependencies, builds the UI, imports
and verifies the dataset, packages everything with PyInstaller, and self-tests the result
(about 2 minutes). Output:

```
dist\SteamStudyTool\SteamStudyTool.exe     <- double-click to run; close the window to quit
```

- No terminal, server or browser needed: the exe starts the local server on a free localhost
  port and opens the app in its own window (Edge WebView2, preinstalled on Windows 10/11). If
  WebView2 is missing, it falls back to the default browser.
- Everything lives **next to the exe**, so the folder can sit on a shared drive (e.g. G:) used
  by several PCs at once:
  ```
  SteamStudyTool.exe
  settings.json          created with defaults on first launch; edited via the gear icon
  data\                  data folder (configurable in Settings)
    catalog.sqlite3      game catalog (read-only while the app runs)
    studies\<appid>.json one file per study ("Add to Studies")
    cache\languages-<PC>.jsonl   Steam language lookups, one file per PC
    logs\<PC>.log
  studiesJPG\            "Export as JPG" output (configurable in Settings)
  ```
  Nothing is written to `%LOCALAPPDATA%`. (Builds before 0.2 used `%LOCALAPPDATA%\SteamStudyTool`;
  that folder held no studies and can be deleted.)
- Rebuilding keeps `settings.json`, `data\` and `studiesJPG\` in `dist\SteamStudyTool`. Copy the
  whole folder to the shared drive; to update it later, copy the new `SteamStudyTool.exe` and
  `_internal\` over the old ones.
- `dist/` and `build/` are git-ignored. `build.bat --no-pause` (or `npm run build-desktop`) is for
  terminal and CI use.

### LLM research (0.5)
"Get more info from LLM" runs Claude Code headless (web search only, no shell or file access,
spend-capped, $0.2-0.5 and about 1 minute per game in tests). It produces:

| Row | How |
|---|---|
| People who worked on it | web research: range, best estimate, confidence, sources |
| Development time | web research: same |
| Cost at €50K per person-year | calculated: people × years × salary; also how long a team of 3 would need |
| Break-even | calculated: cost ÷ (1 − 30% platform cut), in revenue and copies |
| Why it did as well / why not better | from the 40+40 most helpful Steam reviews, with confidence |

Salary, currency and exchange rate, team size, platform cut, model, spend cap and CLI path are
all in Settings. Results are saved to `data\research\<appid>.json`, and the JPG export includes
them.

### The three tabs (0.3)
- **Suggest**: filters, random suggestions, game report (with when and where each number was
  observed), Add to Studies, Export as JPG, and **Get more info from LLM**: a standardized,
  cited research table, run with the Claude Code CLI installed on the PC (see below).
- **Charts**: revenue distribution, games per year, price vs revenue (Studies highlighted; click a
  dot to open the game), tags by median revenue, review count vs score, and the selected game's
  review history. Scope: the qualified catalog by year, or the Suggest tab's filters. Every chart
  has a table view.
- **Data**: update the dataset from Steam, with an estimate of requests and time before you start:
  - update existing games (default: qualified games, reviews and store info, skip if updated
    within 7 days; choose years, scope and parts);
  - add new games (AppIDs after the newest known, plus a quick re-check of recently listed games
    that weren't released yet; **needs a free Steam Web API key**, set in Settings);
  - deep check, about once a year (slow; finds old AppIDs released late and set-aside games
    that took off later; same key);
  - look up languages;
  - update one AppID.

  Jobs run in the background, can be stopped, and continue where they left off. Results are
  shared through the data folder with every PC.

### Features added in 0.2
- **Must support English** filter. Languages come from a one-time, user-started lookup against the
  Steam store (Settings -> Languages; ~35 requests/minute, resumable, shared by all PCs). Games not
  yet checked are kept; only games known to lack English are excluded.
- **Add to Studies** archives a game (one JSON file) and skips it in future suggestions (switch in
  the sidebar). Studies are listed under the session history.
- **Get more info from LLM** shows the research table. The LLM integration itself is not built yet.
- **Export as JPG** saves a compact study sheet (artwork, metrics, pitch, tags, languages) to
  `studiesJPG\<Game> (<AppID>).jpg`. Exporting again overwrites it.
- **Settings** (gear icon): data and export folders, qualification floor, offline mode, language
  lookup, request rate, and Steam/LLM keys for later (stored in plain text in settings.json).

## Setup and run (development)

```bash
npm run setup          # uv sync + npm ci (root and frontend) + Playwright Chromium
npm run import-data    # parse reference HTML -> .local/steam_study.sqlite3 (offline, idempotent)
npm run verify-data    # check counts, SHA-256 and a field-by-field round trip of all 15,521 records
npm run dev            # API on http://127.0.0.1:8765 (docs at /docs) + UI on http://127.0.0.1:5173
```

`npm run start` builds the UI and serves the app and API from one origin at http://127.0.0.1:8765.

## Task contract

| Command | What it does |
|---|---|
| `npm run setup` | Install pinned Python and npm dependencies and Playwright Chromium |
| `npm run import-data` | Import the legacy HTML dataset into SQLite (`--db`, `--source` supported) |
| `npm run verify-data` | Verify the imported DB against the audited legacy figures |
| `npm run dev-api` / `dev-ui` / `dev` | Start the backend, the UI, or both |
| `npm run check` | Ruff (lint and format), Pyright (strict), tsc, ESLint, API contract, pytest, Vitest |
| `npm run test-backend` | Deterministic pytest suite (unit, integration, reference-file checks) |
| `npm run test-frontend` | Vitest and React Testing Library |
| `npm run test-e2e` | Playwright: isolated API and DB, parity against the original HTML, screenshots |
| `npm run test-api-contract` | OpenAPI schema matches `frontend/openapi.json`; generated TS types are up to date |
| `npm run gen-api` | Regenerate `frontend/openapi.json` and `frontend/src/api/schema.ts` |
| `npm run test-live-smoke` | Opt-in live provider smoke tests (none exist before Phase 3) |
| `npm run backup` | Online backup of the SQLite DB to `.local/backups/` |

Playwright artifacts (traces, failure screenshots, `test-results/screenshots/*`) are written to
`test-results/`. View the HTML report with `npx playwright show-report`.

## Configuration

Copy `.env.example` to `.env` to override the defaults: database path, log directory, and the
qualification floor (`STEAM_STUDY_QUALIFICATION_MIN_REVENUE_USD`, default 100000). Logs are JSON
lines in `.local/logs/`.

## Data caveats

Revenue figures are **estimates** (`total reviews x 45 x listed price`), not actual sales. The
legacy dataset is an already filtered 2022-2025 sample with unknown capture dates. Ranks and
percentiles only apply within that legacy population. See
[`docs/revenue-model.md`](docs/revenue-model.md).
