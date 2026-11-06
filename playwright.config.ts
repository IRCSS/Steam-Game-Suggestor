import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 1000 },
  },
  webServer: [
    {
      command: "node scripts/e2e_backend.mjs",
      url: "http://127.0.0.1:8766/api/health",
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: "pipe",
    },
    {
      command: "npm --prefix frontend run dev",
      url: "http://127.0.0.1:5174",
      timeout: 60_000,
      reuseExistingServer: false,
      env: { STEAM_STUDY_API_URL: "http://127.0.0.1:8766", STEAM_STUDY_UI_PORT: "5174" },
    },
  ],
});
