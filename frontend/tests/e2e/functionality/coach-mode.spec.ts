import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Coach Mode Toggle", () => {
  test("toggle is visible in header", async ({ page }) => {
    await loginAs(page);
    await page.goto("/");
    const toggle = page.getByRole("button", { name: /Coach Mode/i });
    await expect(toggle).toBeVisible({ timeout: 10000 });
  });

  test("toggle state persists across navigation", async ({ page }) => {
    await loginAs(page);
    await page.goto("/");
    const toggle = page.getByRole("button", { name: /Coach Mode/i });
    await toggle.click();

    // Navigate away and back
    await page.goto("/game-day");
    await page.goto("/");

    const persistedToggle = page.getByRole("button", { name: /Coach Mode/i });
    await expect(persistedToggle).toBeVisible();
    // Toggle should still appear as amber/active
    await expect(persistedToggle).toHaveClass(/amber|bg-amber/);
  });

  test("toggle can be turned off", async ({ page }) => {
    await loginAs(page);
    await page.goto("/");
    const toggle = page.getByRole("button", { name: /Coach Mode/i });
    await toggle.click(); // turn on
    await toggle.click(); // turn off
    await expect(toggle).not.toHaveClass(/bg-amber-500/);
  });
});
