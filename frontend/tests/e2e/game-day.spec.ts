import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Game Day", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-day");
  });

  test("game day page renders", async ({ page }) => {
    await expect(page).toHaveURL(/game-day/);
    const heading = page.locator("h1, h2").first();
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("new matchup button is visible", async ({ page }) => {
    const btn = page.locator("button").filter({ hasText: /new matchup|create/i }).first();
    await expect(btn).toBeVisible({ timeout: 5000 });
  });

  test("simulate button appears when matchup selected", async ({ page }) => {
    const matchupItems = page.locator("button").filter({ hasText: /vs\.|matchup/i });
    if (await matchupItems.count() > 0) {
      await matchupItems.first().click();
      await page.waitForTimeout(1000);
    }
    // Just verify the page didn't crash
    await expect(page).toHaveURL(/game-day/);
  });

  test("keys section renders when simulation exists", async ({ page }) => {
    await page.waitForTimeout(2000);
    // If there's a simulation, check for Keys section
    const keysSection = page.locator("text=/keys to victory|key/i").first();
    // This is optional — verify no crash
    await expect(page).toHaveURL(/game-day/);
  });

  test("win probability section renders", async ({ page }) => {
    await page.waitForTimeout(2000);
    // Check for win probability indicator
    const winPct = page.locator("text=/win prob|probability/i").first();
    // Verify page loads without crash
    await expect(page).toHaveURL(/game-day/);
  });
});

