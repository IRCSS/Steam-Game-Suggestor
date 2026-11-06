# Steam Study Tool

A Windows desktop app for studying commercially successful indie games on Steam. It suggests
games to study, keeps track of the ones you've studied, charts the market, keeps the data up to
date from Steam, and can research each game with Claude: how many people made it, how long it
took, what it cost, when it broke even, and why players loved it or didn't.

Everything runs locally. The app folder can live on a shared drive (e.g. Google Drive) and be used
from several PCs at once.

## What it does

- **Suggest**: draw a random game from about 3,700 games with an estimated revenue of $100K or
  more, filtered by year, price, revenue, reviews, tags, or English support. Each game gets a
  report: artwork, estimated revenue, rank in its release year, reviews, store pitch and tags.
- **Studies**: "Add to Studies" archives a game so it's never suggested again. "Export as JPG"
  saves a one-image study sheet, ready for a whiteboard such as Miro.
- **LLM research**: one click asks Claude Code for a standard table: team size, development time,
  cost at €50K per person-year, break-even after Steam's 30% cut, and why the game did as well as
  it did and why not better (from the most helpful Steam reviews). Every item has a confidence
  and sources.
- **Charts**: revenue distribution, price vs revenue, tags by median revenue, and more.
- **Data**: add new Steam games, refresh review counts, and look up languages, with the number of
  requests and the time estimated before you start.

Revenue is always an **estimate** (`reviews × 45 × price`), never actual sales. See
[Data and caveats](#data-and-caveats).

## Quick start (Windows)

1. Put the data file in place (see [Getting the data file](#getting-the-data-file)).
2. Install the prerequisites once:
   `winget install Python.Python.3.12 astral-sh.uv OpenJS.NodeJS.LTS`
3. Double-click **`build.bat`** (about 2 minutes). It builds and self-tests the app.
4. Run **`dist\SteamStudyTool\SteamStudyTool.exe`**. To share it, copy the whole
   `dist\SteamStudyTool` folder to a shared drive.

Optional, in Settings (gear icon, top right):
- **Steam Web API key** (free, [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey)):
  only needed for "Add new games" and the yearly deep check.
- **LLM research** uses the [Claude Code](https://code.claude.com/docs/) CLI if it's installed on
  the PC (detected automatically). Each run uses that Claude account: about 1 minute and
  $0.20–0.50, capped at $2 by default.

Everything the app stores sits next to the exe, and rebuilding never touches it:

```
SteamStudyTool.exe
settings.json      settings (created on first run; edit with the gear icon)
data\              game catalog, studies, research, Steam updates, logs
studiesJPG\        exported study sheets
```

## Getting the data file

The app starts from a single file that is **not in this repository**:
`reference/steam_game_suggester.html` (about 11 MB). It is the original one-page Steam game
suggester, with 15,521 games released 2022-2025 embedded, made with
[Steam-Data-Analyzer](https://github.com/IRCSS/Steam-Data-Analyzer) from the public
[Steam Games Dataset](https://www.kaggle.com/datasets/fronkongames/steam-games-dataset).

Copy it to `reference/steam_game_suggester.html` before building. The import checks its SHA-256
and refuses any other file. Without it, `build.bat` and `npm run import-data` stop with a clear
message, and the tests that need it are skipped.

## Data and caveats

- **The starting dataset** is the file above: games released 2022-2025. The Data tab adds newer
  games and fresher numbers from Steam.
- **Estimated revenue** = total reviews × 45 × listed price: a common rule of thumb, not sales
  data. Ranks are within each release year of the local catalog.
- **LLM research** comes from public sources and reviews. Small studios rarely publish team size
  or budgets, so expect "Low"/"Medium" confidence and ranges. Check the linked sources before
  relying on a number.
- **Steam endpoints and SteamSpy** are used politely (rate-limited, user-started, resumable).
  Respect their terms of use.

More: [revenue model](docs/revenue-model.md) · [data dictionary](docs/data-dictionary.md) ·
[architecture](docs/architecture.md) · [design decisions](docs/decisions/).

## For developers

React + TypeScript (Vite) UI, Python 3.12 + FastAPI backend, SQLite catalog, plus per-item JSON
files for anything several PCs write (see [ADR 0003](docs/decisions/0003-shared-folder-storage.md)).
The packaged app is PyInstaller + pywebview.

```bash
npm run setup         # install Python (uv) and npm dependencies + Playwright Chromium
npm run import-data   # build .local/data/catalog.sqlite3 from the reference file (offline)
npm run dev           # API http://127.0.0.1:8765 (docs: /docs) + UI http://127.0.0.1:5173
npm run check         # ruff, pyright (strict), tsc, eslint, API contract, pytest, vitest
npm run test-e2e      # Playwright, fully offline, incl. parity with the original HTML
```

| Path | Contents |
|---|---|
| `backend/app/domain/` | pure logic: filters, suggestions, ranks, charts, research economics |
| `backend/app/api/`, `services.py` | HTTP routes and the service that ties storage to logic |
| `backend/app/providers/`, `research/` | Steam, SteamSpy and Claude Code adapters |
| `backend/app/storage/`, `jobs/` | shared-folder file stores; background data/research jobs |
| `frontend/src/` | the React app (`pages/`: Suggest, Charts, Data) |
| `desktop/`, `scripts/build_desktop.py`, `build.bat` | the Windows app and its build |
| `docs/` | architecture, data dictionary, decisions (ADRs), phase reports |

Tests never touch the network: Steam is faked (`backend/tests/fake_steam.py`) and Claude is
stubbed. Tests that need the local data file skip without it; the end-to-end suite requires it.
After changing the API, run `npm run gen-api`. Notes for coding agents are in
[`CLAUDE.md`](CLAUDE.md); progress and decisions are in `docs/phase-reports/` and
`docs/decisions/`.

Useful extras: `npm run verify-data` (checks the imported catalog against the original file),
`npm run backup` (zips settings, studies, research and caches), `npm run start` (serves the built
UI and API from one port).
