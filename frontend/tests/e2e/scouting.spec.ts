import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Scouting", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/scouting");
  });

  test("scouting page renders", async ({ page }) => {
    await expect(page).toHaveURL(/scouting/);
    const heading = page.locator("h1, h2").first();
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("matchup selector or empty state is visible", async ({ page }) => {
    // Either a matchup selector, or an empty state message
    const hasSelector = await page.locator("select").count() > 0;
    const hasEmptyState = await page.locator("text=/no matchup|select a matchup|create/i").count() > 0;
    expect(hasSelector || hasEmptyState).toBeTruthy();
  });

  test("generate report button exists when matchup selected", async ({ page }) => {
    const select = page.locator("select").first();
    if (await select.count() > 0) {
      const options = await select.locator("option").count();
      if (options > 1) {
        await select.selectOption({ index: 1 });
        const generateBtn = page.locator("button:has-text(/generate|scout/i)").first();
        await expect(generateBtn).toBeVisible({ timeout: 5000 });
      }
    }
  });
});
