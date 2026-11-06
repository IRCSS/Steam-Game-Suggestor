# Phase 0 + 1: Baseline, import, and offline suggestion app at parity

Status: **PASS** (awaiting the user review gate before Phase 2)
Date: 2026-11-06

## Implemented
- **Phase 0:** Git repository, `.gitignore` / `.gitattributes` (the reference HTML stays
  byte-identical), `.env.example`, uv and npm lockfiles, Ruff, Pyright (strict), tsc (strict),
  ESLint, pytest, Vitest, Playwright, OpenAPI-to-TypeScript contract, a CI workflow, and the task
  contract (`npm run setup|import-data|verify-data|dev|check|test-*|backup|gen-api`).
- **Legacy importer:** parses `script#game-data` with an HTML parser, validates strictly against
  the 12 fields, upserts in one transaction, records provenance, adds data-quality flags. It is
  idempotent and leaves session state untouched.
- **Edge-case fixture:** 55 *real* records (`scripts/make_fixture.py`).
- **Phase 1:** schema v1 (`games`, `game_metrics`, `import_runs`, `view_sessions`,
  `view_events`). Pure domain modules port the legacy filtering, lookup, uniform suggestion and
  repeat handling. A $100K qualification gate sits separately from the study filters. FastAPI
  routes cover health, meta, search, resolve, report, count, suggest and session history.
- **React UI** built from the verbatim legacy CSS with the same markup ids and classes:
  sidebar, lookup with autocomplete, tag picker and catalog, game card with on-demand CDN
  artwork and a placeholder, history, toasts, error boundary, and a backend-unavailable state.

## Commands run and results
| Command | Result |
|---|---|
| `npm run import-data` (run twice) | 15,521 inserted, then 0 inserted / 15,521 updated (idempotent), about 5 s |
| `npm run verify-data` | all PASS, including 0 field-by-field mismatches across 15,521 records |
| `npm run check` | PASS: ruff, ruff format, pyright 0 errors, tsc, eslint, contract, **59 pytest**, **19 vitest** |
| `npm run test-e2e` | **22/22 PASS** (1.2 min) |

The Playwright suite covers:
- **Legacy parity**, run live against `reference/steam_game_suggester.html` in the same browser:
  - match counts for 8 filter scenarios (defaults = 1,743);
  - autocomplete results and metadata for 4 queries;
  - the 443-tag catalog, in the same order;
  - field-by-field game report for an exact lookup.
- **Happy path:** filter, suggest, check the Steam URL, copy AppID (clipboard checked), another
  suggestion (no repeat), history, reset, exact AppID lookup that bypasses the filters,
  lookup of a below-floor game, clear history.
- **Repeat exhaustion:** "All seen" appears, then the auto-reset notice; the history is kept.
- Empty and zero-match states.
- No legacy data shipped or fetched by the frontend.
- Screenshots at desktop, tablet and mobile widths with no horizontal overflow.
- No console errors. All external requests are blocked during tests.

Screenshots (gitignored): `test-results/screenshots/{desktop,tablet,mobile}-{empty,game}-{legacy,new}.png`.
Traces are kept on failure under `test-results/`.

## Data integrity
- DB schema version: 1
- Imported games: 15,521. Reference SHA-256 verified (`bdc25ab3…711d88`).
- Qualified games under the $100K model: 3,704
- Legacy rank preservation: PASS (stored and displayed as imported, labelled as legacy-scoped)
- Study state preservation: n/a (Phase 2). Session view events survive re-import (tested).
- Performance: warm `POST /api/suggestions` takes about 13 ms. The first request after start
  takes about 0.8 s while the catalog loads. The production JS bundle is 242 kB, with no data.

## Risks and deviations
See [`docs/decisions/0001-phase-1-deviations.md`](../decisions/0001-phase-1-deviations.md).
In short:
- TypeScript is pinned to 5.9 for tooling compatibility.
- Price 0 shows as "$0.00", not "Free".
- A few small, labelled UI additions.
- `view_events` retention is unbounded.
- `npm audit` reports 10 moderate advisories, all in **dev-only** lint tooling
  (typescript-eslint dependencies). Nothing ships at runtime.

The plan's defaults table was checked against the HTML and is correct: the minimum positive
review score is 50%. The JS fallback of 0 only applies to an empty field.

## How to run
`npm run setup && npm run import-data && npm run dev`, then open http://127.0.0.1:5173.

## Next phase gate (Phase 2: persistent study workflow)
Please confirm visual and functional parity first. Then Phase 2 adds:
- `study_status` and `study_notes` (migration 002) and their APIs;
- status actions on the card;
- a Studies page;
- exclusion switches;
- export and import;
- tests showing that re-import never resets statuses or notes.
