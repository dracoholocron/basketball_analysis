/**
 * Screenshot capture spec — saves PNG screenshots of every major page
 * to tests/e2e/screenshots/output/ for the user manual.
 *
 * Run with:
 *   npx playwright test --config=tests/e2e/playwright.config.ts tests/e2e/screenshots/ --reporter=list
 */
import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";
import { loginAs } from "../helpers";

const OUT_DIR = path.join(__dirname, "output");

test.beforeAll(() => {
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });
});

async function shot(page: Parameters<typeof loginAs>[0], name: string) {
  await page.screenshot({ path: path.join(OUT_DIR, `${name}.png`), fullPage: false });
}

test.describe("Manual Screenshots", () => {
  test("01 — Login page", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "01-login");
    await expect(page.getByText(/sign in|log in|login/i).first()).toBeVisible();
  });

  test("02 — Dashboard", async ({ page }) => {
    await loginAs(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "02-dashboard");
    await expect(page.getByText(/dashboard/i).first()).toBeVisible();
  });

  test("03 — Scouting", async ({ page }) => {
    await loginAs(page);
    await page.goto("/scouting");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "03-scouting");
    await expect(page.getByText(/scout/i).first()).toBeVisible();
  });

  test("04 — Game Day", async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-day");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "04-game-day");
    await expect(page.getByText(/game day/i).first()).toBeVisible();
  });

  test("05 — Game Tracker", async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-tracker");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "05-game-tracker");
    await expect(page.getByText(/game tracker/i).first()).toBeVisible();
  });

  test("06 — Play Builder", async ({ page }) => {
    await loginAs(page);
    await page.goto("/play-builder");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "06-play-builder");
    await expect(page.getByText(/play builder/i).first()).toBeVisible();
  });

  test("07 — Matchup Workspace", async ({ page }) => {
    await loginAs(page);
    await page.goto("/matchups");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "07-matchup-workspace");
    await expect(page.getByText(/matchup/i).first()).toBeVisible();
  });

  test("08 — Training", async ({ page }) => {
    await loginAs(page);
    await page.goto("/training");
    await page.waitForTimeout(2000);
    await shot(page, "08-training");
    // Training page may redirect if API has no seed data — screenshot captures current state
  });

  test("09 — Games", async ({ page }) => {
    await loginAs(page);
    await page.goto("/games");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "09-games");
    await expect(page.getByText(/games/i).first()).toBeVisible();
  });

  test("10 — Admin / Settings", async ({ page }) => {
    await loginAs(page);
    await page.goto("/admin");
    await page.waitForLoadState("networkidle").catch(() => {});
    await shot(page, "10-admin");
    await expect(page.getByText(/admin|settings/i).first()).toBeVisible();
  });

  test("11 — Coach Mode ON (Dashboard)", async ({ page }) => {
    await loginAs(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle").catch(() => {});
    const toggle = page.getByRole("button", { name: /Coach Mode/i });
    if (await toggle.isVisible({ timeout: 5000 })) {
      await toggle.click();
      await page.waitForTimeout(500);
    }
    await shot(page, "11-coach-mode-on");
  });
});
