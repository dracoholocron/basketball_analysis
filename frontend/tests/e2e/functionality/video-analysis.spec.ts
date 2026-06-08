/**
 * E2E tests for video analysis features on the game detail page.
 *
 * These tests use API route mocking (page.route) so they do NOT require a live
 * backend with real data. The mocks simulate:
 * - A game with id MOCK_GAME_ID
 * - A completed analysis job (status = done)
 * - Player metrics with display_label (#1, #2...)
 * - An active/running job to test button disabling
 */
import { test, expect, Page } from "@playwright/test";

const MOCK_GAME_ID = "00000000-0000-0000-0000-000000000001";
const MOCK_JOB_ID = "00000000-0000-0000-0000-000000000002";

async function mockGameApis(page: Page, jobStatus: string = "done") {
  // Mock GET /api/v1/games/:id
  await page.route(`**/api/v1/games/${MOCK_GAME_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: MOCK_GAME_ID,
        location: "Test Arena",
        game_date: "2024-12-15",
        court_level: "NBA",
        is_half_court: false,
      }),
    })
  );

  // Mock GET /api/v1/games/:id/metrics
  await page.route(`**/api/v1/games/${MOCK_GAME_ID}/metrics`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        game_id: MOCK_GAME_ID,
        job_id: MOCK_JOB_ID,
        total_frames: 1440,
        team1_possession_pct: 52.0,
        team2_possession_pct: 48.0,
        team1_passes: 30,
        team2_passes: 25,
        team1_interceptions: 4,
        team2_interceptions: 3,
        players: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            job_id: MOCK_JOB_ID,
            track_id: 641,
            display_label: "#1",
            team_id: 1,
            total_distance_m: 680.5,
            avg_speed_kmh: 14.2,
            max_speed_kmh: 24.7,
            possession_frames: 80,
            passes_made: 5,
            interceptions_made: 1,
          },
          {
            id: "22222222-2222-2222-2222-222222222222",
            job_id: MOCK_JOB_ID,
            track_id: 872,
            display_label: "#2",
            team_id: 2,
            total_distance_m: 520.0,
            avg_speed_kmh: 11.5,
            max_speed_kmh: 19.3,
            possession_frames: 55,
            passes_made: 3,
            interceptions_made: 2,
          },
        ],
      }),
    })
  );

  // Mock GET /api/v1/games/:id/cv-events
  await page.route(`**/api/v1/games/${MOCK_GAME_ID}/cv-events`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    })
  );

  // Mock GET /api/v1/jobs?game_id=...&status=done  (auto-load last done job)
  await page.route(
    (url) =>
      url.pathname.includes("/api/v1/jobs") &&
      url.searchParams.get("status") === "done" &&
      url.searchParams.get("game_id") === MOCK_GAME_ID,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          jobStatus === "done"
            ? [
                {
                  id: MOCK_JOB_ID,
                  game_id: MOCK_GAME_ID,
                  status: "done",
                  current_stage: "complete",
                  progress_pct: 100,
                },
              ]
            : []
        ),
      })
  );

  // Mock GET /api/v1/jobs?game_id=...&status=running (active job check)
  await page.route(
    (url) =>
      url.pathname.includes("/api/v1/jobs") &&
      url.searchParams.get("status") === "running" &&
      url.searchParams.get("game_id") === MOCK_GAME_ID,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          jobStatus === "running"
            ? [
                {
                  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                  game_id: MOCK_GAME_ID,
                  status: "running",
                  current_stage: "player_tracking",
                  progress_pct: 30,
                },
              ]
            : []
        ),
      })
  );

  // Mock GET /api/v1/jobs?game_id=...&status=pending
  await page.route(
    (url) =>
      url.pathname.includes("/api/v1/jobs") &&
      url.searchParams.get("status") === "pending" &&
      url.searchParams.get("game_id") === MOCK_GAME_ID,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
  );
}

test.describe("Video analysis UI", () => {
  test.beforeEach(async ({ page }) => {
    // Inject a fake auth token to simulate a logged-in state without
    // depending on the real auth API (all API calls in these tests are mocked).
    await page.context().addCookies([
      {
        name: "access_token",
        value: "fake-test-token-for-e2e",
        domain: "localhost",
        path: "/",
      },
    ]);
  });

  test("test_analyze_button_disabled_when_job_running", async ({ page }) => {
    await mockGameApis(page, "running");
    await page.goto(`/games/${MOCK_GAME_ID}`);
    await page.waitForLoadState("networkidle");

    const analyzeBtn = page
      .locator("button")
      .filter({ hasText: /analizar|re-analizar/i });
    await expect(analyzeBtn).toBeVisible({ timeout: 8000 });
    await expect(analyzeBtn).toBeDisabled({ timeout: 8000 });
  });

  test("test_player_table_shows_display_label", async ({ page }) => {
    await mockGameApis(page, "done");
    await page.goto(`/games/${MOCK_GAME_ID}`);
    await page.waitForLoadState("networkidle");

    // Switch to Players tab
    const playersTab = page.locator("button").filter({ hasText: /jugadores/i });
    await expect(playersTab).toBeVisible({ timeout: 8000 });
    await playersTab.click();

    // Table should show #1, #2 instead of raw track IDs like 641, 872
    await expect(page.locator("td").filter({ hasText: "#1" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator("td").filter({ hasText: "#2" })).toBeVisible({
      timeout: 5000,
    });
    // Raw track IDs should NOT appear in the table
    await expect(page.locator("td").filter({ hasText: "641" })).not.toBeVisible();
  });

  test("test_speed_values_show_kmh_format", async ({ page }) => {
    await mockGameApis(page, "done");
    await page.goto(`/games/${MOCK_GAME_ID}`);
    await page.waitForLoadState("networkidle");

    const playersTab = page.locator("button").filter({ hasText: /jugadores/i });
    await playersTab.click();

    // Speeds should be formatted as XX.X km/h
    const speedCell = page.locator("td").filter({ hasText: /km\/h/ }).first();
    await expect(speedCell).toBeVisible({ timeout: 5000 });
  });

  test("test_inline_video_player_appears_for_done_job", async ({ page }) => {
    await mockGameApis(page, "done");
    await page.goto(`/games/${MOCK_GAME_ID}`);
    await page.waitForLoadState("networkidle");

    // Video element should be auto-loaded via the second useEffect
    const videoEl = page.locator("video");
    await expect(videoEl).toBeVisible({ timeout: 8000 });
  });

  test("test_analyze_button_enabled_when_no_active_job", async ({ page }) => {
    await mockGameApis(page, "done");
    await page.goto(`/games/${MOCK_GAME_ID}`);
    await page.waitForLoadState("networkidle");

    const analyzeBtn = page
      .locator("button")
      .filter({ hasText: /re-analizar|analizar/i });
    await expect(analyzeBtn).toBeVisible({ timeout: 8000 });
    await expect(analyzeBtn).not.toBeDisabled({ timeout: 8000 });
  });
});
