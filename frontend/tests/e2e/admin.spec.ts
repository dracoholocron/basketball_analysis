import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Admin pages", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("admin box scores page renders", async ({ page }) => {
    await page.goto("/admin/box-scores");
    await expect(page).toHaveURL(/box-scores/);
    const heading = page.locator("h1, h2").first();
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("admin dashboard shows navigation cards", async ({ page }) => {
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/admin/);
    await page.waitForTimeout(2000);
    // Should have navigation cards
    const orgsCard = page.locator("text=/organizations/i").first();
    await expect(orgsCard).toBeVisible({ timeout: 5000 });
    const seasonsCard = page.locator("text=/seasons/i").first();
    await expect(seasonsCard).toBeVisible({ timeout: 5000 });
  });

  test("admin organizations sub-page renders", async ({ page }) => {
    await page.goto("/admin/organizations");
    await expect(page).toHaveURL(/admin\/organizations/);
    await page.waitForTimeout(2000);
    const heading = page.locator("h1, h2").first();
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("admin teams sub-page renders", async ({ page }) => {
    await page.goto("/admin/teams");
    await expect(page).toHaveURL(/admin\/teams/);
    await page.waitForTimeout(2000);
    const heading = page.locator("h1, h2").first();
    await expect(heading).toBeVisible({ timeout: 5000 });
  });

  test("play builder page renders", async ({ page }) => {
    await page.goto("/play-builder");
    await expect(page).toHaveURL(/play-builder/);
    await page.waitForTimeout(2000);
    const svg = page.locator("svg").first();
    await expect(svg).toBeVisible({ timeout: 5000 });
  });

  test("play builder export PDF button exists", async ({ page }) => {
    await page.goto("/play-builder");
    await page.waitForTimeout(3000);
    const pdfBtn = page.locator("button").filter({ hasText: /pdf/i }).first();
    await expect(pdfBtn).toBeVisible({ timeout: 8000 });
  });

  test("play builder share button exists", async ({ page }) => {
    await page.goto("/play-builder");
    await page.waitForTimeout(3000);
    const shareBtn = page.locator("button").filter({ hasText: /share|copy/i }).first();
    await expect(shareBtn).toBeVisible({ timeout: 8000 });
  });

  test("play builder can load a play from library", async ({ page }) => {
    await page.goto("/play-builder");
    await page.waitForTimeout(3000);
    // Click first play in library if available
    const playItems = page.locator("button").filter({ hasText: /pick & roll|horns|flex/i });
    if (await playItems.count() > 0) {
      await playItems.first().click();
      await page.waitForTimeout(1000);
      // Canvas should still be present
      const svg = page.locator("svg").first();
      await expect(svg).toBeVisible({ timeout: 3000 });
    }
  });
});

