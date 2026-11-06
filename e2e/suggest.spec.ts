import { expect, setToggle, settledCount, test } from "./fixtures";

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test("happy path: filter, suggest, copy, avoid repeats, reset, lookup", async ({
  page,
  consoleErrors,
}) => {
  await page.goto("/");
  await expect(page.locator(".dataset-badge")).toContainText("3,704 qualified games");
  await expect(page.locator(".dataset-badge")).toContainText("15,521 in catalog");
  expect(await settledCount(page)).toBe("1,743 matches");
  await expect(page.locator("#emptyState")).toBeVisible();

  // Choose filters: drop 2022 and add a tag through the browsable catalog.
  await setToggle(page.locator('.year-checkbox[value="2022"]'), false);
  await page.locator(".tag-browser summary").click();
  await page.locator("#tagSearch").fill("rogue");
  await page.locator('.available-tag[data-tag="Rogue-lite"]').click();
  await expect(page.locator("#selectedTags .selected-tag")).toHaveCount(1);
  await expect(page.locator("#includeTags")).toHaveValue("Rogue-lite");
  const filtered = await settledCount(page);
  expect(filtered).toMatch(/^\d[\d,]* matches$/);
  expect(filtered).not.toBe("1,743 matches");

  // Suggest.
  await page.locator("#suggestButton").click();
  const title = page.locator("#gameTitle");
  await expect(title).not.toBeEmpty();
  const first = await title.textContent();
  const appidChip = await page.locator(".hero-chip", { hasText: "AppID" }).textContent();
  const appid = appidChip!.replace(/\D/g, "");
  await expect(page.locator("#steamLink")).toHaveAttribute(
    "href",
    `https://store.steampowered.com/app/${appid}`,
  );
  await expect(page.locator("#steamLink")).toHaveAttribute("target", "_blank");
  await expect(page.locator("#gameTags .tag").first()).toBeVisible();
  // Artwork is blocked offline -> local placeholder.
  await expect(page.locator("#heroImage")).toHaveAttribute("src", /^data:image\/svg\+xml/);

  // Copy AppID.
  await page.locator("#copyAppIdButton").click();
  await expect(page.locator("#toast")).toHaveText(`Copied AppID ${appid}.`);
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(appid);

  // Another suggestion avoids the repeat; history lists both.
  await page.locator("#anotherButton").click();
  await expect(title).not.toHaveText(first!);
  await expect(page.locator(".history-item")).toHaveCount(2);

  // Reset filters.
  await page.locator("#resetButton").click();
  await expect(page.locator("#toast")).toHaveText("Filters reset.");
  await expect(page.locator("#minRevenue")).toHaveValue("150000");
  await expect(page.locator("#includeTags")).toHaveValue("");
  await expect(page.locator('.year-checkbox[value="2022"]')).toBeChecked();

  // Exact AppID lookup bypasses filters ($42M is outside the default $150K-$800K segment).
  await page.locator("#gameLookup").fill("1794680");
  await page.locator(".lookup-result").first().waitFor();
  await page.locator("#gameLookup").press("Enter");
  await expect(title).toHaveText("Vampire Survivors");
  await expect(page.locator("#toast")).toHaveText("Loaded Vampire Survivors.");
  await expect(page.locator("#gameRevenue")).toHaveText("$42.1M");
  await expect(page.locator(".history-item")).toHaveCount(3);
  await expect(page.locator(".history-item").first()).toContainText("Vampire Survivors");

  // A legacy game below the $100K floor is still reachable by lookup and flagged.
  await page.locator("#gameLookup").fill("Melody's Escape 2");
  await page.locator(".lookup-result", { hasText: "Melody's Escape 2" }).first().click();
  await expect(title).toHaveText("Melody's Escape 2");
  await expect(page.getByTestId("below-floor")).toContainText("Below $100K catalog floor");

  // Clear history.
  await page.locator("#clearHistoryButton").click();
  await expect(page.locator("#historyPanel")).toHaveCount(0);
  await expect(page.locator("#toast")).toHaveText("Session history cleared.");

  expect(consoleErrors).toEqual([]);
});

test("avoid repeats exhausts a small pool, then resets session history", async ({
  page,
  consoleErrors,
}) => {
  await page.goto("/");
  await settledCount(page);
  for (const year of ["2022", "2024", "2025"]) {
    await setToggle(page.locator(`.year-checkbox[value="${year}"]`), false);
  }
  await page.locator("#includeTags").fill("Rhythm");
  expect(await settledCount(page)).toBe("4 matches");

  const seen = new Set<string>();
  for (let i = 0; i < 4; i++) {
    await page.locator("#suggestButton").click();
    await expect(page.locator(".history-item")).toHaveCount(i + 1);
    seen.add((await page.locator("#gameTitle").textContent())!);
  }
  expect(seen.size).toBe(4);
  await expect(page.locator("#matchCount")).toHaveText("All seen");
  await expect(page.locator("#suggestButton")).toBeEnabled();

  await page.locator("#suggestButton").click();
  await expect(page.locator("#toast")).toHaveText(
    "All matching games had been shown. Repeat history reset.",
  );
  await expect(page.locator(".history-item")).toHaveCount(4); // history kept, distinct
  expect(await settledCount(page)).toBe("3 matches");
  expect(consoleErrors).toEqual([]);
});

test("empty state and zero matches", async ({ page, consoleErrors }) => {
  await page.goto("/");
  await settledCount(page);
  await page.locator("#includeTags").fill("definitely-not-a-tag");
  expect(await settledCount(page)).toBe("0 matches");
  await expect(page.locator("#suggestButton")).toBeDisabled();
  await page.locator("#gameLookup").fill("zzzz-no-such-game");
  await page.locator("#gameLookup").press("Enter");
  await expect(page.locator("#toast")).toHaveText("No matching game found.");
  await expect(page.locator("#emptyState")).toBeVisible();
  // The browser logs the (expected) 404 from /api/games/resolve; nothing else is allowed.
  expect(consoleErrors.filter((e) => !e.includes("status of 404"))).toEqual([]);
});

test("frontend does not ship or fetch the legacy dataset", async ({ page }) => {
  // Dev-mode Vite serves large unbundled vendor chunks, so check content, not raw size:
  // no response may contain legacy dataset records, and API payloads stay compact.
  const responses: { url: string; body: string }[] = [];
  page.on("response", async (res) => {
    const body = await res.text().catch(() => "");
    responses.push({ url: res.url(), body });
  });
  await page.goto("/");
  await settledCount(page);
  await page.waitForLoadState("networkidle");
  expect(responses.length).toBeGreaterThan(3);
  for (const { url, body } of responses) {
    expect(body, url).not.toContain("qualifying_games_in_year");
    expect(body, url).not.toContain("game-data");
    if (url.includes("/api/")) expect(body.length, url).toBeLessThan(100_000);
  }
});
