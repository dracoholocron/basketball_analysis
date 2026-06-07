import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Game Tracker", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-tracker");
  });

  test("game tracker page renders", async ({ page }) => {
    await expect(page).toHaveURL(/game-tracker/);
    const heading = page.locator("h1, h2").first();
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("scoreboard shows team scores", async ({ page }) => {
    await page.waitForTimeout(2000);
    const hasMatchup = await page.locator("select").count() > 0;
    if (hasMatchup) {
      // Scoreboard shows "Your Team" and "Opponent" labels
      const scoreText = page.locator("text=/Your Team|Opponent/i").first();
      await expect(scoreText).toBeVisible({ timeout: 5000 });
    } else {
      const emptyState = page.locator("text=/matchup|game day/i").first();
      await expect(emptyState).toBeVisible({ timeout: 5000 });
    }
  });

  test("court svg is rendered when matchup available", async ({ page }) => {
    await page.waitForTimeout(2000);
    const hasMatchup = await page.locator("select").count() > 0;
    if (hasMatchup) {
      const court = page.locator("svg").first();
      await expect(court).toBeVisible({ timeout: 5000 });
    }
  });

  test("sync indicator is shown", async ({ page }) => {
    await page.waitForTimeout(2000);
    const hasMatchup = await page.locator("select").count() > 0;
    if (hasMatchup) {
      const syncIndicator = page.locator("text=/synced|sync/i").first();
      await expect(syncIndicator).toBeVisible({ timeout: 8000 });
    }
  });

  test("heat map toggle buttons are present when matchup available", async ({ page }) => {
    await page.waitForTimeout(2500);
    const hasMatchup = await page.locator("select").count() > 0;
    if (hasMatchup) {
      // The toggle says "Heat" not "Heat map"
      const heatBtn = page.locator("button").filter({ hasText: /^Heat$/i });
      await expect(heatBtn).toBeVisible({ timeout: 5000 });
      const shotsBtn = page.locator("button").filter({ hasText: /^Shots$/i });
      await expect(shotsBtn).toBeVisible({ timeout: 5000 });
    }
  });

  test("can switch between heat map modes", async ({ page }) => {
    await page.waitForTimeout(2500);
    const hasMatchup = await page.locator("select").count() > 0;
    if (hasMatchup) {
      const heatBtn = page.locator("button").filter({ hasText: /^Heat$/i });
      if (await heatBtn.count() > 0) {
        await heatBtn.click();
        await expect(page.locator("svg").first()).toBeVisible({ timeout: 3000 });
      }
    }
  });
});

