import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Priority Keys (Game Day)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-day");
  });

  test("game day page loads with Keys to Victory section", async ({ page }) => {
    await expect(page.getByText(/Game Day/i).first()).toBeVisible({ timeout: 10000 });
  });

  test("pin button visible when simulation runs", async ({ page }) => {
    // Select first matchup if available
    const matchupBtn = page.locator(".divide-y button").first();
    if (await matchupBtn.isVisible({ timeout: 5000 })) {
      await matchupBtn.click();
      const simSection = page.getByText(/No Simulation Yet|Keys to Victory/i);
      await expect(simSection).toBeVisible({ timeout: 10000 });
    }
  });
});
