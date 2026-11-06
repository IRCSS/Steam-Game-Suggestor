# Data dictionary (catalog schema version 2)

Source: `backend/app/db/migrations/001_initial.sql`.

## `games`: one row per game
| Column | Meaning |
|---|---|
| `appid` | Steam AppID (primary key, stable identity) |
| `name`, `short_description` | as imported; rendered as text only |
| `release_year` | year only; `release_date` stays NULL until verified |
| `price_minor_units`, `currency_code` | legacy price x 100, `USD`; context in `price_display_context` |
| `price_display_context` | `legacy_price_context_unknown`: capture date, sale state and region unknown |
| `is_free` | NULL = unknown. A legacy price of 0 is **not** treated as proof of free-to-play |
| `tags_json` | trimmed, non-empty tags (used for display and matching) |
| `tags_raw_json` | tags exactly as imported (560 records had stray whitespace) |
| `data_source` | `legacy_html` |

## `game_metrics`: metric snapshots
The legacy import creates exactly one row per AppID with `is_legacy_snapshot = 1` (unique partial
index), so re-imports upsert instead of duplicating.

| Column | Meaning |
|---|---|
| `observed_at` | NULL for legacy (collection date unknown); `imported_at` is the import time |
| `source` | `legacy_import` |
| `total_reviews`, `review_score` | legacy snapshot values |
| `legacy_price` | exact imported price (REAL) |
| `legacy_estimated_revenue` | exact imported estimate (integer USD); `estimated_revenue_minor_units` = x 100 |
| `estimate_model`, `estimate_params_json` | `legacy_reviews_x45_price`, `{"reviews_to_sales_multiplier": 45}` |
| `legacy_rank_in_year`, `legacy_qualifying_games_in_year`, `legacy_revenue_percentile_in_year` | apply to the legacy population only |
| `legacy_source_index` | position in the original JSON array |
| `data_quality_flags` | JSON list, e.g. `price_zero_f2p_unverified`, `empty_description`, `tags_whitespace_trimmed`, `legacy_revenue_formula_mismatch` (0 occurrences) |

## `import_runs`
Provenance of each import: source file name, SHA-256, record/inserted/updated counts, timestamp.

## Removed in migration 002: `view_sessions`, `view_events`
Session view history is now kept in memory per app process (`app/domain/session.py`).

## Files in the data folder (not in SQLite; see ADR 0003)
| Path | Content |
|---|---|
| `studies/<appid>.json` | `schema_version`, `appid`, `name`, `status` ("study"), `added_at`, `added_by` (PC name), `updated_at`, `notes`, `research` (reserved for LLM results). Unknown keys preserved. |
| `cache/languages-<pc>.jsonl` | one line per lookup: `appid`, `status` (`ok`/`unavailable`), `languages` (list), `fetched_at`, `source` |
| `catalog.version` | version of the installed catalog (source SHA + schema) |
| `logs/<pc>.log`, `logs/launcher-<pc>.log` | JSON logs |

`settings.json` (next to the exe): `version`, `data_dir`, `export_dir`,
`qualification_min_revenue_usd`, `offline_mode`, `steam.{api_key, store_requests_per_minute}`,
`llm.{provider, model, api_key}`.

## Audited legacy figures (verified by `npm run verify-data` and tests)
15,521 records and unique AppIDs. Years: 2022: 3,946; 2023: 4,244; 2024: 4,982; 2025: 2,349.
3,704 games have an estimated revenue of $100K or more; 1,004 have price 0; there are 443
distinct trimmed tags; 2 descriptions are empty; 1,009 names are non-ASCII. Default legacy
filters match **1,743** games, the same as the original HTML.
