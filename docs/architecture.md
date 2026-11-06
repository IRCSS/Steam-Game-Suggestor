# Architecture (Phase 1)

```text
Browser: React + TypeScript (Vite)       frontend/src
   |  same-origin /api (Vite proxy in dev; FastAPI serves frontend/dist in `npm run start`)
FastAPI routes (thin)                     backend/app/api/*.py
   |  Pydantic contracts                  backend/app/schemas/games.py  -> frontend/openapi.json
Application service                       backend/app/services.py (StudyService)
   |-- domain (pure, no I/O)              backend/app/domain/{filters,lookup,suggestion,qualification,revenue,models}.py
   |-- repository (SQL only)              backend/app/db/{queries,connection}.py + migrations/
SQLite (WAL, foreign keys)                .local/steam_study.sqlite3
Importer                                  backend/app/importer.py + scripts/import_legacy_html.py
```

## Key decisions

- **Filtering runs in Python, over an in-memory catalog.** The ~15.5k compact legacy records are
  loaded once and reloaded automatically when a new `import_runs` row appears. Domain functions
  port the legacy JS one to one: inclusive bounds, the legacy fallbacks for empty fields, and
  substring tag matching (AND for required tags, OR for excluded). This gives exact parity, and a
  count or suggestion takes a few milliseconds. SQL filtering can be added later if the catalog
  grows by orders of magnitude.
- **Original source order is preserved** (`game_metrics.legacy_source_index`). The legacy name
  search breaks ties by array order, so this is needed for identical autocomplete results.
- **Session state is server-side but session-scoped.** The UI generates a session id per page
  load, which matches the legacy "current session". `view_events` records suggestions and manual
  lookups. `view_sessions` holds two event-id markers: the repeat-reset marker (set on the
  "all seen" auto-reset; the visible history is kept) and the history-clear marker (the Clear
  button). Showing a game never changes any persistent study status.
- **The qualification gate is separate from the study filters.** `CatalogPolicy` applies the
  $100K floor (configurable) before the user's filters. "Include below catalog floor" turns on an
  exploration mode. Exact lookup always bypasses both the gate and the filters.
- **Contracts:** FastAPI's OpenAPI schema is exported to `frontend/openapi.json`, and TypeScript
  types are generated from it (`openapi-typescript`). A backend test and `gen-api:check` fail if
  either goes stale.
- **Security:** binds to 127.0.0.1. State-changing requests with a non-local `Origin` get 403
  (CSRF guard). Store text is rendered as React text, never through `dangerouslySetInnerHTML`.
  No secrets exist yet.
- **Observability:** JSON logs (stderr and a rotating file in `.local/logs`) with a per-request
  `rid`, which is also returned as the `x-request-id` header.

## API (Phase 1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | version, schema version, game count, `needs_import` |
| GET | `/api/meta` | dataset counts/scope, years, 443 tags, legacy default filters |
| GET | `/api/games?q=&limit=` | legacy autocomplete (AppID exact, then name prefix, then legacy rank) |
| GET | `/api/games/resolve?q=` | legacy "Load game report" (AppID, exact name, best match) |
| GET | `/api/games/{appid}` | compact game report (plan section 6.1 shape) |
| POST | `/api/suggestions/count` | match count for filters and session (`all_seen` flag) |
| POST | `/api/suggestions` | uniform random pick; records the view; optional `seed` |
| GET | `/api/sessions/{id}/history` | last 12 distinct games shown |
| POST | `/api/sessions/{id}/views` | record a manual lookup |
| POST | `/api/sessions/{id}/clear` | clear the session history and seen set |
