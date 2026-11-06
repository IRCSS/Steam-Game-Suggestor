// Playwright webServer for the API: fresh isolated app folder, offline legacy import, uvicorn.
// Layout mirrors the packaged app: <app>/settings.json, <app>/data/catalog.sqlite3, <app>/studiesJPG
import { execSync, spawn } from "node:child_process";
import { copyFileSync, mkdirSync, rmSync } from "node:fs";

export const E2E_APP_DIR = ".local/e2e-app";
rmSync(E2E_APP_DIR, { recursive: true, force: true });

// Offline: no Steam requests (artwork proxy returns 404, language lookups are refused).
const env = { ...process.env, STEAM_STUDY_APP_DIR: E2E_APP_DIR, STEAM_STUDY_OFFLINE: "1" };
// Saved LLM research for one game (tests never call Claude).
mkdirSync(`${E2E_APP_DIR}/data/research`, { recursive: true });
copyFileSync("e2e/data/research-1794680.json", `${E2E_APP_DIR}/data/research/1794680.json`);
execSync(`uv run python scripts/import_legacy_html.py --db ${E2E_APP_DIR}/data/catalog.sqlite3`, {
  stdio: "inherit",
  env,
});
const server = spawn("uv run uvicorn app.main:app --host 127.0.0.1 --port 8766", {
  shell: true,
  stdio: "inherit",
  env,
});
const stop = () => server.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
server.on("exit", (code) => process.exit(code ?? 0));
