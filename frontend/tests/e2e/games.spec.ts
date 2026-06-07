import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Games", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/games");
  });

  test("games page renders", async ({ page }) => {
    await expect(page).toHaveURL(/games/);
    // Should have a heading or title
    const heading = page.locator("h1, h2, [data-testid=page-title]").first();
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("shows create game button or form", async ({ page }) => {
    const createBtn = page.locator("button").filter({ hasText: /new game|create|upload/i }).first();
    await expect(createBtn).toBeVisible({ timeout: 5000 });
  });
});
