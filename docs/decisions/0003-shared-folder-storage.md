# ADR 0003: Data next to the exe, safe on a shared drive; studies as files

Status: accepted. Date: 2026-11-06. Supersedes the storage parts of ADR 0002 and plan section 3.1
(`study_status`, `study_notes`, and `view_events` in SQLite).

## Context
The user runs the packaged app from a shared drive (G:) on several PCs **at the same time**.
They want data next to the exe (not `%LOCALAPPDATA%`), a settings file next to the exe, and an
in-app settings UI. SQLite is not safe for concurrent writers over network or cloud-synced
filesystems: locking is unreliable, WAL needs shared memory, and sync clients create conflict
copies.

## Decision
- `settings.json` sits next to the exe and is created with defaults when missing. If it is
  unreadable it is set aside as `settings.invalid-<time>.json`. Unknown keys are preserved.
  Relative paths resolve against the exe folder. The gear-icon dialog edits it, and changes apply
  without a restart (the service is rebuilt).
- Data folder (default `data\`, configurable):
  - `catalog.sqlite3`: **read-only** at runtime (`mode=ro`, plus `immutable=1` in the packaged
    app, so there is no locking). Only the importer and build write it. The exe installs or
    refreshes it from the bundled seed, keyed by `catalog.version` (source SHA + schema).
  - `studies/<appid>.json`: one file per study, written atomically (temp file + rename). PCs
    adding different games never touch the same file. Readers re-scan every 5 seconds and skip
    unreadable files.
  - `cache/languages-<pc>.jsonl`: per-PC, append-only language lookups. Reads merge all shards,
    newest `fetched_at` wins, and partially synced last lines are ignored.
  - `logs/<pc>.log`, `logs/launcher-<pc>.log`.
- Session view history (avoid repeats, last 12) moved **in memory** per app process. Migration
  002 drops `view_events` and `view_sessions`.
- The embedded browser runs in private mode, so no WebView2 profile is written to
  `%LOCALAPPDATA%`.
- `build.bat` keeps `settings.json`, `data\`, `studiesJPG\` and `backups\` in
  `dist\SteamStudyTool` when rebuilding.

## "Must support English"
The legacy dataset has no language data. Following the user's choice, languages come from the
Steam store `appdetails?filters=basic` endpoint (verified live on 2026-11-06; about 5 KB per call,
only `supported_languages` is kept). This is a user-started background job: 35 requests/minute
by default; on HTTP 429 or 5xx it backs off exponentially, honouring Retry-After (4 attempts);
cancel and resume are supported. This brings a slice of Phase 3 forward. The filter excludes only
games **known** to lack English; unchecked games stay in, and the UI says how many are checked.

## Consequences
- Multiple PCs can use the app at once without corrupting shared state. Two PCs editing the
  *same* study at the same moment means last write wins (acceptable for this workflow).
- API keys (future) live in plain text in a shared settings.json; the UI warns about this.
- Studies are not in SQLite, so future features (notes, LLM research) extend the per-study JSON
  (`notes`, `research` fields are already reserved).
- Offline mode (Settings, or `STEAM_STUDY_OFFLINE=1`, which tests use) disables all Steam calls.
