import type { Page } from "@playwright/test";
import { LEGACY_URL, expect, settledCount, test } from "./fixtures";

// Side-by-side visual baselines of the legacy HTML and the new app at comparable widths.
// Written to test-results/screenshots (gitignored); inspected manually, not pixel-diffed,
// because the new app intentionally adds provenance labels.
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "tablet", width: 900, height: 1100 },
  { name: "mobile", width: 390, height: 844 },
];

async function loadVampire(page: Page) {
  await page.locator("#gameLookup").fill("1794680");
  await page.locator("#gameLookup").press("Enter");
  await expect(page.locator("#gameTitle")).toHaveText("Vampire Survivors");
  await page.locator("#toast").evaluate((el) => el.classList.remove("visible"));
  await page.waitForTimeout(400);
}

for (const vp of VIEWPORTS) {
  test(`screenshots @ ${vp.name}`, async ({ browser, page, consoleErrors }) => {
    const out = (app: string, state: string) =>
      `test-results/screenshots/${vp.name}-${state}-${app}.png`;

    const legacy = await browser.newPage({ viewport: vp });
    await legacy.route(/^https?:/, (r) => r.abort());
    await legacy.goto(LEGACY_URL);
    await expect(legacy.locator("#matchCount")).toHaveText(/matches/);
    await legacy.screenshot({ path: out("legacy", "empty"), fullPage: true });
    await loadVampire(legacy);
    await legacy.screenshot({ path: out("legacy", "game"), fullPage: true });
    await legacy.close();

    await page.setViewportSize(vp);
    await page.goto("/");
    await settledCount(page);
    await page.screenshot({ path: out("new", "empty"), fullPage: true });
    await loadVampire(page);
    await page.screenshot({ path: out("new", "game"), fullPage: true });

    // No horizontal overflow at any width.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    expect(consoleErrors).toEqual([]);
  });
}
