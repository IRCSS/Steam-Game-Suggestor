import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { expect, settledCount, setToggle, test } from "./fixtures";

const APP_DIR = path.resolve(import.meta.dirname, "..", ".local", "e2e-app");
const API = "http://127.0.0.1:8766";
const VAMPIRE = 1794680;

test.afterEach(async ({ request }) => {
  // Keep the shared e2e app folder clean for other specs.
  const studies = await (await request.get(`${API}/api/studies`)).json();
  for (const item of studies.items) await request.delete(`${API}/api/studies/${item.appid}`);
});

async function loadGame(page: import("@playwright/test").Page, query: string) {
  await page.locator("#gameLookup").fill(query);
  await page.locator("#gameLookup").press("Enter");
  await expect(page.locator("#gameTitle")).not.toBeEmpty();
}

test("Add to Studies archives the game and removes it from suggestions", async ({
  page,
  consoleErrors,
}) => {
  await page.goto("/");
  const before = await settledCount(page);
  expect(before).toBe("1,743 matches");

  await page.locator("#suggestButton").click();
  const title = (await page.locator("#gameTitle").textContent())!;
  await page.locator("#studyButton").click();
  await expect(page.locator("#toast")).toContainText(`Added ${title} to Studies`);
  await expect(page.locator("#studyButton")).toHaveText("✓ In Studies");
  await expect(page.locator("#studiesPanel .history-item")).toHaveCount(1);
  await expect(page.locator("#studiesPanel")).toContainText(title);

  // The study file exists in the data folder next to the app.
  const files = readdirSync(path.join(APP_DIR, "data", "studies"));
  expect(files).toHaveLength(1);

  // Excluded from suggestions: with avoid-repeats OFF the pool shrinks by exactly one.
  await setToggle(page.locator("#avoidRepeats"), false);
  expect(await settledCount(page)).toBe("1,742 matches");
  await setToggle(page.locator("#excludeStudies"), false);
  expect(await settledCount(page)).toBe("1,743 matches");

  // Removing asks for confirmation.
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#studyButton").click();
  await expect(page.locator("#studyButton")).toHaveText("＋ Add to Studies");
  await expect(page.locator("#studiesPanel")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("Export as JPG writes a compact image to studiesJPG", async ({ page, consoleErrors }) => {
  await page.goto("/");
  await settledCount(page);
  await loadGame(page, String(VAMPIRE));
  await page.locator("#exportJpegButton").click();
  await expect(page.locator("#toast")).toHaveText(
    "Saved to studiesJPG: Vampire Survivors (1794680).jpg",
    { timeout: 20_000 },
  );
  const file = path.join(APP_DIR, "studiesJPG", "Vampire Survivors (1794680).jpg");
  const bytes = readFileSync(file);
  expect([...bytes.subarray(0, 3)]).toEqual([0xff, 0xd8, 0xff]);
  expect(bytes.length).toBeGreaterThan(50_000);
  // Width 1200 CSS px at pixelRatio 2 -> 2400 px wide JPEG (SOF0 marker holds the size).
  const sof = bytes.indexOf(Buffer.from([0xff, 0xc0]));
  expect(bytes.readUInt16BE(sof + 7)).toBe(2400);
  await expect(page.getByTestId("export-card")).toHaveCount(0); // off-screen sheet removed
  // The artwork request is the only one that fails (offline proxy -> placeholder).
  expect(consoleErrors.filter((e) => !e.includes("status of 404"))).toEqual([]);
});

test("Get more info from LLM explains why research cannot run (offline)", async ({ page }) => {
  await page.goto("/");
  await settledCount(page);
  await page.locator("#suggestButton").click(); // default segment: never Vampire Survivors
  await expect(page.locator("#gameTitle")).not.toBeEmpty();
  await expect(page.getByTestId("research-panel")).toHaveCount(0); // no saved research
  await page.locator("#researchButton").click();
  await expect(page.getByTestId("research-panel")).toContainText("Offline mode is on");
  await expect(page.getByRole("button", { name: "Run research" })).toHaveCount(0);
  await page.locator("#researchButton").click();
  await expect(page.getByTestId("research-panel")).toHaveCount(0);
});

test("Must support English keeps unchecked games and explains why", async ({ page }) => {
  await page.goto("/");
  const before = await settledCount(page);
  await setToggle(page.locator("#requireEnglish"), true);
  expect(await settledCount(page)).toBe(before); // nothing looked up yet -> nothing excluded
  await expect(page.locator(".toggle-row", { hasText: "Must support English" })).toContainText(
    "Checked 0 of 3,704 qualified games",
  );
  await loadGame(page, String(VAMPIRE));
  await expect(page.locator("#gameLanguages")).toContainText("Not checked yet");
});

test("Settings dialog shows paths next to the app and applies changes", async ({ page }) => {
  await page.goto("/");
  await settledCount(page);
  await page.locator("#settingsButton").click();
  const dialog = page.getByRole("dialog", { name: "Settings" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(path.join(APP_DIR, "data"));
  await expect(dialog).toContainText(path.join(APP_DIR, "studiesJPG"));
  await expect(dialog.getByTestId("offline-forced")).toContainText("forced on");
  await expect(dialog).toContainText("started from the Data tab");

  // Raise the floor -> qualified badge shrinks; then restore.
  await dialog.locator("#settingsFloor").fill("1000000");
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("#toast")).toHaveText("Settings saved.");
  await expect(page.locator(".dataset-badge")).not.toContainText("3,704 qualified");
  const saved = JSON.parse(readFileSync(path.join(APP_DIR, "settings.json"), "utf-8"));
  expect(saved.qualification_min_revenue_usd).toBe(1000000);

  await dialog.locator("#settingsFloor").fill("100000");
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator(".dataset-badge")).toContainText("3,704 qualified");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("saved LLM research opens with the game and is part of the JPG", async ({ page }) => {
  await page.goto("/");
  await loadGame(page, String(VAMPIRE));
  const panel = page.getByTestId("research-panel");
  await expect(panel).toBeVisible(); // opens automatically when research exists
  const table = page.getByTestId("research-table");
  await expect(table).toContainText("1–3 people (best 2)");
  await expect(table).toContainText("10–14 months (best 12)");
  await expect(table).toContainText("Cost at €50K per person-year");
  await expect(table).toContainText("≈ €100K"); // 2 people x 12 months x €50K
  await expect(table).toContainText("after the 30% platform cut");
  await expect(page.getByTestId("insights-worked")).toContainText("Fixture reason it worked");
  await expect(page.getByTestId("insights-held-back")).toContainText("Fixture bottleneck");
  // Offline in tests: a new run cannot be started.
  await expect(page.getByRole("button", { name: "Refresh research" })).toBeDisabled();

  await page.locator("#exportJpegButton").click();
  await expect(page.locator("#toast")).toContainText("Vampire Survivors (1794680).jpg", { timeout: 20_000 });
  const bytes = readFileSync(path.join(APP_DIR, "studiesJPG", "Vampire Survivors (1794680).jpg"));
  const sof = bytes.indexOf(Buffer.from([0xff, 0xc0]));
  const height = bytes.readUInt16BE(sof + 5);
  expect(height).toBeGreaterThan(2000); // 1,646 px without research: extended down with it
});
