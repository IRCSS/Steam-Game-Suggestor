-- 002: session view history moved to an in-memory, per-process store.
-- The catalog database is shared read-only (possibly on a network/cloud drive) and must not be
-- written during normal use. User-authored state (studies) lives in per-item JSON files.
DROP TABLE IF EXISTS view_events;
DROP TABLE IF EXISTS view_sessions;
