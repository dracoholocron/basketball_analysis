import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("loads dashboard with navigation", async ({ page }) => {
    await expect(page).toHaveURL(/\/$|dashboard/);
    // Sidebar should be visible
    await expect(page.locator("nav, aside, [data-testid=sidebar]").first()).toBeVisible();
  });

  test("sidebar links are visible", async ({ page }) => {
    const sidebarLinks = ["Games", "Scouting", "Game Day", "Game Tracker", "Play Builder"];
    for (const link of sidebarLinks) {
      const locator = page.locator(`a:has-text("${link}"), button:has-text("${link}")`).first();
      await expect(locator).toBeVisible({ timeout: 5000 });
    }
  });

  test("can navigate to games page", async ({ page }) => {
    await page.click(`a:has-text("Games"), button:has-text("Games")`);
    await expect(page).toHaveURL(/games/, { timeout: 5000 });
  });
});
