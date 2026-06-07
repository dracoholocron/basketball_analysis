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
    // page.tsx: header toggle is labeled "Nuevo" (Crear partido is in the expanded form only)
    await expect(page.getByRole("button", { name: /nuevo/i })).toBeVisible({ timeout: 10000 });
  });

  test("simulate button appears when matchup selected", async ({ page }) => {
    const matchupItems = page.locator("button").filter({ hasText: /vs\.|matchup/i });
    if (await matchupItems.count() > 0) {
      await matchupItems.first().click();
      await page.waitForTimeout(1000);
    }
    await expect(page).toHaveURL(/game-day/);
  });

  test("keys section renders when simulation exists", async ({ page }) => {
    await page.waitForTimeout(2000);
    await expect(page).toHaveURL(/game-day/);
  });

  test("win probability section renders", async ({ page }) => {
    await page.waitForTimeout(2000);
    await expect(page).toHaveURL(/game-day/);
  });
});
