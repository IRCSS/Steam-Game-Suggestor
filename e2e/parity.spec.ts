import type { Page } from "@playwright/test";
import { LEGACY_URL, expect, matchCount, setToggle, settledCount, test } from "./fixtures";

/**
 * Parity against the ORIGINAL reference HTML: identical filter inputs must produce identical
 * match counts and lookup results. The new app's catalog floor is disabled ("include below floor")
 * because the legacy app has no qualification gate.
 */
interface Scenario {
  name: string;
  years?: number[];
  fields?: Record<string, string>;
}

const SCENARIOS: Scenario[] = [
  { name: "legacy defaults" },
  { name: "2024 only", years: [2024] },
  { name: "no revenue bounds", fields: { minRevenue: "", maxRevenue: "" } },
  {
    name: "tags include/exclude",
    fields: { includeTags: "Roguelike, Pixel", excludeTags: "Multiplayer", maxRevenue: "" },
  },
  { name: "price + score", fields: { minPrice: "5", maxPrice: "20", minReviewScore: "90" } },
  {
    name: "rank/percentile/reviews",
    fields: { minPercentile: "95", maxReviews: "5000", minRank: "10", maxRank: "500", maxRevenue: "" },
  },
  {
    name: "widest (empty fields use legacy fallbacks)",
    fields: { minRevenue: "", maxRevenue: "", maxPrice: "", maxRank: "", minReviews: "", minReviewScore: "" },
  },
  { name: "nothing selected", years: [] },
];

async function apply(page: Page, s: Scenario) {
  if (s.years) {
    for (const box of await page.locator(".year-checkbox").all()) {
      const year = Number(await box.getAttribute("value"));
      await setToggle(box, s.years.includes(year));
    }
  }
  for (const [id, value] of Object.entries(s.fields ?? {})) {
    await page.locator(`#${id}`).fill(value);
  }
}

test.describe("legacy parity", () => {
  let legacy: Page;

  test.beforeAll(async ({ browser }) => {
    legacy = await browser.newPage();
    await legacy.route(/^https?:/, (r) => r.abort());
    await legacy.goto(LEGACY_URL);
    await expect(legacy.locator("#matchCount")).toHaveText(/matches/);
  });

  test.afterAll(async () => {
    await legacy.close();
  });

  for (const scenario of SCENARIOS) {
    test(`match count: ${scenario.name}`, async ({ page }) => {
      await legacy.reload();
      await apply(legacy, scenario);
      const expected = await matchCount(legacy);

      await page.goto("/");
      await settledCount(page);
      await setToggle(page.locator("#includeBelowThreshold"), true);
      await apply(page, scenario);
      await expect.poll(() => matchCount(page)).toBe(expected);
      test.info().annotations.push({ type: "count", description: `${scenario.name}: ${expected}` });
    });
  }

  test("defaults agree with and without the $100K gate", async ({ page }) => {
    await legacy.reload();
    const expected = await matchCount(legacy);
    expect(expected).toBe("1,743 matches");
    await page.goto("/");
    expect(await settledCount(page)).toBe(expected); // gate ON (default)
    await setToggle(page.locator("#includeBelowThreshold"), true);
    await expect.poll(() => matchCount(page)).toBe(expected);
  });

  for (const query of ["vampire", "souls", "1794680", "the"]) {
    test(`lookup results: "${query}"`, async ({ page }) => {
      await legacy.reload();
      await legacy.locator("#gameLookup").fill(query);
      const expected = await legacy.locator(".lookup-result-name").allTextContents();
      const expectedMeta = await legacy.locator(".lookup-result-meta").allTextContents();

      await page.goto("/");
      await page.locator("#gameLookup").fill(query);
      await expect(page.locator(".lookup-result-name")).toHaveCount(expected.length);
      const norm = (xs: string[]) => xs.map((x) => x.replace(/\s+/g, " ").trim());
      expect(norm(await page.locator(".lookup-result-name").allTextContents())).toEqual(norm(expected));
      expect(norm(await page.locator(".lookup-result-meta").allTextContents())).toEqual(
        norm(expectedMeta),
      );
    });
  }

  test("tag catalog matches legacy", async ({ page }) => {
    await legacy.reload();
    const expected = await legacy.locator(".available-tag").evaluateAll((els) =>
      els.map((e) => (e as HTMLElement).dataset.tag),
    );
    await page.goto("/");
    const actual = await page.locator(".available-tag").evaluateAll((els) =>
      els.map((e) => (e as HTMLElement).dataset.tag),
    );
    expect(actual).toHaveLength(443);
    expect(actual).toEqual(expected);
  });

  test("game report fields match legacy for an exact lookup", async ({ page }) => {
    const read = async (p: Page) =>
      Object.fromEntries(
        await Promise.all(
          ["gameTitle", "gameRank", "gamePercentile", "gameReviews", "gameReviewScore", "gameDescription", "rankCardValue"].map(
            async (id) => [id, (await p.locator(`#${id}`).textContent())?.replace(/\s+/g, " ").trim()],
          ),
        ),
      );
    await legacy.reload();
    await legacy.locator("#gameLookup").fill("1794680");
    await legacy.locator("#gameLookup").press("Enter");
    await expect(legacy.locator("#gameTitle")).toHaveText("Vampire Survivors");

    await page.goto("/");
    await page.locator("#gameLookup").fill("1794680");
    await page.locator("#gameLookup").press("Enter");
    await expect(page.locator("#gameTitle")).toHaveText("Vampire Survivors");
    expect(await read(page)).toEqual(await read(legacy));
    const legacyTags = await legacy.locator("#gameTags .tag").allTextContents();
    const tags = await page.locator("#gameTags .tag").allTextContents();
    expect(tags.map((t) => t.trim())).toEqual(legacyTags.map((t) => t.trim()));
  });
});
