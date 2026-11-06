import { expect, settledCount, test } from "./fixtures";

test("tabs keep state; Charts are scoped and consistent; dots open games", async ({
  page,
  consoleErrors,
}) => {
  await page.goto("/");
  await settledCount(page);
  await expect(page.getByRole("tab")).toHaveText(["Suggest", "Charts", "Data"]);

  // Load a game, switch tabs, come back: the game is still there.
  await page.locator("#gameLookup").fill("1794680");
  await page.locator("#gameLookup").press("Enter");
  await expect(page.locator("#gameTitle")).toHaveText("Vampire Survivors");

  await page.getByRole("tab", { name: "Charts" }).click();
  await expect(page).toHaveURL(/#charts$/);
  const kpis = page.getByTestId("chart-kpis");
  await expect(kpis).toContainText("3,704"); // qualified catalog, all years
  await expect(page.getByTestId("chart-scope")).toContainText("est. revenue >= $100,000");
  await expect(page.locator(".chart-card")).toHaveCount(6);
  await expect(page.locator(".chart-card svg.recharts-surface").first()).toBeVisible();

  // Table view of the distribution sums to the scope count.
  const revenueCard = page.locator(".chart-card", { hasText: "Estimated revenue distribution" });
  await revenueCard.getByRole("button", { name: "Table" }).click();
  const counts = await revenueCard.locator("tbody tr td:nth-child(2)").allTextContents();
  expect(counts.reduce((sum, c) => sum + Number(c.replace(/,/g, "")), 0)).toBe(3704);

  // Year filter narrows everything.
  await page.locator(".chart-filters .chip", { hasText: "2024" }).click();
  await expect(page.getByTestId("chart-scope")).toContainText("2024");
  await expect(kpis).not.toContainText("3,704");

  // Same filters as the Suggest tab -> the Suggest tab's match count (studies included).
  await page.getByLabel("Same filters as the Suggest tab").check();
  await expect(kpis).toContainText("1,743");

  // History card shows the current game.
  await expect(page.locator(".chart-card", { hasText: "Review history: Vampire Survivors" })).toBeVisible();
  await expect(page.getByTestId("history-empty")).toBeVisible();

  // Clicking a dot opens that game in the Suggest tab.
  await page.getByLabel("Qualified catalog").check();
  const dot = page.locator(".chart-card", { hasText: "Price vs estimated revenue" }).locator(".recharts-scatter-symbol").first();
  await dot.click({ force: true });
  await expect(page).toHaveURL(/#suggest$/);
  await expect(page.locator("#gameTitle")).not.toHaveText("Vampire Survivors");
  await expect(page.locator("#gameTitle")).not.toBeEmpty();

  expect(consoleErrors).toEqual([]);
});

test("Data tab shows the catalog and is safely disabled offline", async ({ page, consoleErrors }) => {
  await page.goto("/#data");
  await expect(page.getByRole("tab", { name: "Data" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("data-stats")).toContainText("15,521");
  await expect(page.getByRole("alert")).toContainText("Offline mode is on");
  for (const name of ["Update games", "Find new games", "Run deep check", "Look up languages"]) {
    await expect(page.getByRole("button", { name })).toBeDisabled();
  }
  // Estimates still work offline (no requests are made).
  await expect(page.getByTestId("refresh-estimate")).toContainText("3,704 games");
  await expect(page.getByTestId("languages-estimate")).toContainText("3,704 games");
  await page.locator("#refresh-year-2025").click();
  await expect(page.getByTestId("refresh-estimate")).not.toContainText("3,704 games");
  await expect(page.locator("#discover-title")).toBeVisible();
  await expect(page.getByText("not set", { exact: true })).toBeVisible(); // API key hint
  expect(consoleErrors).toEqual([]);
});

test("screenshots of the Charts and Data tabs", async ({ page }) => {
  await page.goto("/#charts");
  await expect(page.getByTestId("chart-kpis")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: "test-results/screenshots/desktop-charts-new.png", fullPage: true });
  await page.goto("/#data");
  await expect(page.getByTestId("refresh-estimate")).toContainText("games");
  await page.screenshot({ path: "test-results/screenshots/desktop-data-new.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#charts");
  await expect(page.getByTestId("chart-kpis")).toBeVisible();
  await page.waitForTimeout(500);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: "test-results/screenshots/mobile-charts-new.png", fullPage: true });
});
