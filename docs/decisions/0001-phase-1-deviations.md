# ADR 0001: Phase 0/1 implementation choices and deviations from the plan

Status: accepted (pending user review at the Phase 1 gate). Date: 2026-11-06.

1. **TypeScript pinned to ~5.9.** TypeScript 7 and 6 are newer than the peer ranges of
   `typescript-eslint` (<6.1) and `openapi-typescript` (^5). Upgrade once those packages support
   them.
2. **Simplified backend layout.** There is a single `services.py` (the application service) and
   a single `schemas/games.py`. The domain, repository and route layers stay separate as the plan
   requires. There is no `api/studies.py`, `charts.py` and so on until their phases.
3. **API additions beyond the plan's draft table:** `GET /api/games/resolve` (the legacy "Load
   game report" semantics) and `/api/sessions/{id}/{history,views,clear}` (session history). The
   match count is `POST /api/suggestions/count` (with the filter body), as the plan allows.
4. **In-memory filtering** instead of SQL (see `docs/architecture.md`), for exact legacy parity.
5. **Price 0 is displayed as "$0.00", not "Free"** (legacy). This avoids implying free-to-play
   status (plan section 3.2, invariant 3).
6. **Small, labelled UI additions:** a qualified-count badge (3,704 of 15,521), the
   "Est. gross revenue" label, a provenance line, a "Below $100K catalog floor" chip on
   looked-up games, an "Include below catalog floor" toggle, and clickable history items (they
   reopen a game's report). Everything else, including CSS, markup ids and texts, matches the
   legacy page.
7. **Lower-casing:** Python `str.lower()` replaces JS `toLocaleLowerCase()`. The parity tests
   show identical results on this dataset.
8. **Retention:** `view_events` is unbounded for now (one row per shown game). Retention and
   compaction controls are deferred to Phase 2, where longer-term "seen" history is decided.
9. **Known legacy behavior kept:** the autocomplete dropdown covers the "Load game report"
   button while it is open. Pressing Enter or clicking a result works, as in the legacy page.
