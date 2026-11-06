-- 001_initial: games, legacy metric snapshots, import provenance, session view events.

CREATE TABLE games (
    appid                 INTEGER PRIMARY KEY,
    name                  TEXT NOT NULL,
    short_description     TEXT,
    release_year          INTEGER,
    release_date          TEXT,               -- ISO date only when verified; NULL for legacy
    price_minor_units     INTEGER,            -- NULL = unknown (not zero)
    currency_code         TEXT,
    price_display_context TEXT,               -- e.g. legacy_price_context_unknown
    is_free               INTEGER,            -- NULL = unknown; legacy price 0 is NOT proof of F2P
    tags_json             TEXT NOT NULL DEFAULT '[]',  -- trimmed, non-empty display tags
    tags_raw_json         TEXT,               -- tags exactly as imported (whitespace preserved)
    tags_source           TEXT,
    tags_fetched_at       TEXT,
    developer             TEXT,
    publisher             TEXT,
    data_source           TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE INDEX idx_games_release_year ON games(release_year);
CREATE INDEX idx_games_name_nocase ON games(name COLLATE NOCASE);

CREATE TABLE import_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path   TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    record_count  INTEGER NOT NULL,
    inserted      INTEGER NOT NULL,
    updated       INTEGER NOT NULL,
    imported_at   TEXT NOT NULL
);

CREATE TABLE game_metrics (
    id                                INTEGER PRIMARY KEY AUTOINCREMENT,
    appid                             INTEGER NOT NULL REFERENCES games(appid),
    observed_at                       TEXT,            -- NULL for legacy: capture date unknown
    imported_at                       TEXT NOT NULL,
    source                            TEXT NOT NULL,   -- legacy_import | steam_* (later)
    total_reviews                     INTEGER,
    positive_reviews                  INTEGER,
    review_score                      REAL,
    price_minor_units                 INTEGER,
    currency_code                     TEXT,
    price_type                        TEXT,
    legacy_price                      REAL,            -- exact imported price value
    estimated_revenue_minor_units     INTEGER,
    legacy_estimated_revenue          INTEGER,         -- exact imported estimated_revenue value
    estimate_model                    TEXT,
    estimate_params_json              TEXT,
    legacy_rank_in_year               INTEGER,
    legacy_qualifying_games_in_year   INTEGER,
    legacy_revenue_percentile_in_year REAL,
    legacy_source_index               INTEGER,         -- position in the original JSON array
    is_legacy_snapshot                INTEGER NOT NULL DEFAULT 0,
    data_quality_flags                TEXT NOT NULL DEFAULT '[]'
);

-- Exactly one legacy snapshot per AppID makes re-import idempotent.
CREATE UNIQUE INDEX uq_game_metrics_legacy ON game_metrics(appid) WHERE is_legacy_snapshot = 1;
CREATE INDEX idx_game_metrics_appid ON game_metrics(appid);

CREATE TABLE view_sessions (
    session_id                     TEXT PRIMARY KEY,
    created_at                     TEXT NOT NULL,
    -- Events with id <= these markers are ignored for "seen" / history respectively.
    repeat_reset_after_event_id    INTEGER NOT NULL DEFAULT 0,
    history_cleared_after_event_id INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE view_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES view_sessions(session_id),
    appid      INTEGER NOT NULL REFERENCES games(appid),
    shown_at   TEXT NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('suggested', 'manual_lookup'))
);

CREATE INDEX idx_view_events_session ON view_events(session_id, id);
