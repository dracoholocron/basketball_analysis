import { test, expect } from "@playwright/test";
import { loginAs } from "./helpers";

test.describe("Games", () => {
  test.beforeEach(async ({ page }) => {
    // Mock the games list so the page doesn't redirect on 401 (fake token)
    await page.route("**/api/v1/games*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0, skip: 0, limit: 20 }),
      })
    );
    await page.route("**/api/v1/seasons*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      })
    );
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

test.describe("Game detail — auto-load done job", () => {
  /**
   * These tests require:
   * - A game with id TEST_GAME_ID env var set, which already has a completed job.
   * - Running API + DB seeded with at least one done job for that game.
   *
   * If TEST_GAME_ID is not set, tests are skipped gracefully.
   */
  const gameId = process.env.TEST_GAME_ID;

  test.beforeEach(async ({ page }) => {
    if (!gameId) test.skip();
    await loginAs(page);
    await page.goto(`/games/${gameId}`);
  });

  test("game_page_loads_last_done_job", async ({ page }) => {
    // The auto-load useEffect should populate the job status card without user action
    const jobCard = page.locator("text=Análisis completado").or(page.locator("text=done"));
    await expect(jobCard).toBeVisible({ timeout: 10000 });
  });

  test("inline_video_player_visible_when_done", async ({ page }) => {
    // Video element should appear when a done job is loaded
    const videoEl = page.locator("video");
    await expect(videoEl).toBeVisible({ timeout: 10000 });
  });

  test("download_button_present_when_done", async ({ page }) => {
    const downloadLink = page.locator("a").filter({ hasText: /Descargar video anotado|Download/i });
    await expect(downloadLink).toBeVisible({ timeout: 10000 });
  });
});
