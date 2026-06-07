/**
 * Deterministic screenshot capture for the user manual.
 * Run with: npm run docs:screenshots
 * 
 * Requires a running dev/preview server with seeded test data.
 * Set TEST_EMAIL and TEST_PASSWORD env vars to a valid admin account.
 */
import { test, Page } from "@playwright/test";
import path from "path";

const SCREENSHOTS_DIR = path.join(__dirname, "../../docs/user-manual/screenshots");
const EMAIL = process.env.TEST_EMAIL ?? "admin@test.com";
const PASS = process.env.TEST_PASSWORD ?? "admin123";

async function shot(page: Page, slug: string, selector?: string) {
  const filepath = path.join(SCREENSHOTS_DIR, `${slug}.png`);
  if (selector) {
    const el = page.locator(selector).first();
    if (await el.isVisible({ timeout: 5000 })) {
      await el.screenshot({ path: filepath, animations: "disabled" });
      return;
    }
  }
  await page.screenshot({ path: filepath, fullPage: false, animations: "disabled" });
}

async function login(page: Page) {
  await page.goto("/login");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.fill("input[type=email], input[name=email]", EMAIL);
  await page.fill("input[type=password], input[name=password]", PASS);
  await page.click("button[type=submit]");
  await page.waitForURL(/\/$|dashboard/, { timeout: 15000 });
}

test.describe("Manual Screenshots", () => {
  test("01 Login page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await shot(page, "01-login");
  });

  test("02 Dashboard", async ({ page }) => {
    await login(page);
    await page.waitForLoadState("networkidle");
    await shot(page, "02-dashboard");
  });

  test("03 Game Day — Keys to Victory", async ({ page }) => {
    await login(page);
    await page.goto("/game-day");
    await page.waitForLoadState("networkidle");
    await shot(page, "07-game-day-keys");
  });

  test("04 Coach Mode toggle", async ({ page }) => {
    await login(page);
    await page.goto("/game-day");
    const toggle = page.getByRole("button", { name: /Coach Mode/i });
    await toggle.click();
    await shot(page, "09-game-day-coach-mode");
  });

  test("05 Game Tracker — 3 column layout", async ({ page }) => {
    await login(page);
    await page.goto("/game-tracker");
    await page.waitForLoadState("networkidle");
    await shot(page, "10-game-tracker-3col");
  });

  test("06 Play Builder canvas", async ({ page }) => {
    await login(page);
    await page.goto("/play-builder");
    await page.waitForLoadState("networkidle");
    await shot(page, "17-play-builder-canvas");
  });

  test("07 Training sessions list", async ({ page }) => {
    await login(page);
    await page.goto("/training");
    await page.waitForLoadState("networkidle");
    await shot(page, "23-training-list");
  });

  test("08 Matchup Workspace tabs", async ({ page }) => {
    await login(page);
    await page.goto("/matchups");
    await page.waitForLoadState("networkidle");
    await shot(page, "26-matchup-workspace-tabs");
  });

  test("09 Admin dashboard", async ({ page }) => {
    await login(page);
    await page.goto("/admin");
    await page.waitForLoadState("networkidle");
    await shot(page, "28-admin-dashboard");
  });

  test("10 Mobile — Game Tracker", async ({ page }) => {
    await login(page);
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/game-tracker");
    await page.waitForLoadState("networkidle");
    await shot(page, "10-game-tracker-3col-mobile");
  });
});
