// Playwright webServer for the API: fresh isolated DB, offline legacy import, then uvicorn.
import { execSync, spawn } from "node:child_process";
import { rmSync } from "node:fs";

const db = ".local/e2e.sqlite3";
for (const suffix of ["", "-wal", "-shm"]) rmSync(db + suffix, { force: true });

const env = { ...process.env, STEAM_STUDY_DB: db, STEAM_STUDY_LOG_DIR: ".local/e2e-logs" };
execSync(`uv run python scripts/import_legacy_html.py --db ${db}`, { stdio: "inherit", env });
const server = spawn(
  "uv run uvicorn app.main:app --host 127.0.0.1 --port 8766",
  { shell: true, stdio: "inherit", env },
);
const stop = () => server.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
server.on("exit", (code) => process.exit(code ?? 0));
