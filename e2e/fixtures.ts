import { test as base, expect, type Locator, type Page } from "@playwright/test";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const LEGACY_URL = pathToFileURL(
  path.resolve(import.meta.dirname, "..", "reference", "steam_game_suggester.html"),
).href;

const LOCAL = /^(http:\/\/127\.0\.0\.1(:\d+)?\/|file:|data:|blob:)/;

/**
 * Every test runs fully offline: any request that leaves 127.0.0.1 (e.g. Steam CDN artwork) is
 * aborted, so artwork falls back to the local placeholder. Console errors on the new app fail
 * the test (aborted external images are expected and filtered).
 */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: [
    async ({ context, page }, use, testInfo) => {
      const blocked: string[] = [];
      await context.route("**/*", (route) => {
        const url = route.request().url();
        if (LOCAL.test(url)) return route.continue();
        blocked.push(url);
        return route.abort();
      });
      const errors: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() !== "error") return;
        if (msg.text().includes("net::ERR_FAILED")) return; // blocked external artwork
        errors.push(msg.text());
      });
      page.on("pageerror", (err) => errors.push(err.message));
      await use(errors);
      if (blocked.length) testInfo.annotations.push({ type: "blocked-external", description: String(blocked.length) });
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Legacy CSS visually hides the real checkbox inside `label.switch` / `label.year-option`, so
 * Playwright's check() never sees it as actionable. Click the wrapping label, like a user would.
 */
export async function setToggle(input: Locator, checked: boolean): Promise<void> {
  if ((await input.isChecked()) !== checked) {
    await input.locator("xpath=ancestor::label[1]").click();
  }
  await expect(input).toBeChecked({ checked });
}

export async function matchCount(page: Page): Promise<string> {
  return (await page.locator("#matchCount").textContent())?.trim() ?? "";
}

/** Wait until the new app's debounced count has settled on a value. */
export async function settledCount(page: Page): Promise<string> {
  let last = "";
  await expect
    .poll(
      async () => {
        const now = await matchCount(page);
        const stable = now === last && now !== "Calculating…";
        last = now;
        return stable;
      },
      { intervals: [250, 250, 250, 500, 500, 1000] },
    )
    .toBe(true);
  return last;
}
