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

## Setup and run

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
