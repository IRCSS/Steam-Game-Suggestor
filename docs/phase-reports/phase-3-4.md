# Phases 3 + 4: Steam data sync and charts, in three tabs

Status: **PASS**
Date: 2026-11-06. Design: [ADR 0004](../decisions/0004-sync-charts-tabs.md)

## Implemented
- **Tabs:** Suggest · Charts · Data. Language lookups moved from Settings into the Data tab.
- **Data tab:**
  - status tiles;
  - live job panel (progress, ETA, counters, log, Stop);
  - four actions with options and live estimates:
    - **Update existing games** (scope, years, parts, staleness);
    - **Add new games** (since the last AppID; needs a Steam Web API key; Test key);
    - **Look up languages**;
    - **Update one AppID**.
- **Steam providers:** reviews (all languages), store details, SteamSpy tags, official app list.
- **Observation storage:** per PC, append-only, merged on read. The catalog database is never
  written.
- **Ranks:** recomputed over the local catalog; exact legacy reproduction verified; scope labelled.
- **Charts tab:**
  - scope filters (qualified catalog by year, or the Suggest tab's filters);
  - headline stat tiles;
  - revenue distribution, games per year, price vs revenue (Studies highlighted, click to open),
    tags by median revenue (with sample sizes), review count vs score, and per-game review
    history;
  - tooltips and a table view on every chart.
- **Game report provenance:** where and when reviews, price and tags were observed, plus the
  legacy rank. Settings shows when offline mode is forced by the environment.

## Verification
| Check | Result |
|---|---|
| `npm run check` | PASS: ruff, pyright strict (0 errors), tsc, eslint, API contract, **98 pytest**, **27 vitest** |
| `npm run test-e2e` | **30/30 PASS**, including legacy parity (counts, lookups, tags, report) after the rank refactor |
| Rank identity | recomputed ranks equal legacy ranks for all 15,521 games (test) |
| Live, packaged exe | Vampire Survivors: 250,334 → 252,733 reviews, $3.74 → $4.99 undiscounted, tags and English filled in, rank #16 → #14 (labelled local catalog). A 3-game refresh used 6 requests. |
| `build.bat` | PASS (111 s, 61 MB), smoke test OK, user files in `dist` kept |

Steam requests made during development: about 20 in total (endpoint probes and the live check
above). Automated tests use fakes (`backend/tests/fake_steam.py`) and never reach the network.

## Known limitations
- **Adding new games needs a Steam Web API key** (free); everything else is keyless.
- Late releases are covered since 0.4 (see "Addendum" below).
- **A full refresh of all 3,704 qualified games takes about 2 hours** at the default 35
  requests/minute. It is resumable.
- Steam's limits for these endpoints are not published. On repeated 429s, lower the rate in
  Settings.

## Next
- Phase 5, LLM research: decide the fields, provider and key.
- Phase 6 remainder: backup/restore UI, single-instance guard.

## Addendum 0.4 (2026-11-06): late releases, set-aside games, new years
- "Add new games" also re-checks recently listed games that weren't released yet (capped).
- New **Deep check** button for the yearly sweep: games changed on Steam (including old AppIDs)
  and every set-aside game. Status tiles show set-aside counts and the last deep check.
- Suggest tab: new release years appear ticked; untouched defaults (e.g. worst rank) follow the
  data.
- Fixed: the deep check could not be started when nothing was known in advance.
- Tests: 101 pytest, 30 vitest, 30 Playwright.
