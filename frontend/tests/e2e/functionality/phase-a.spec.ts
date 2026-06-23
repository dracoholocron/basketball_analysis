import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

// Phase A UI fixes. Specs mock the API so they run against the frontend without a live backend.

test.describe("Phase A — heatmap empty-state", () => {
  test("shows empty-state message when there are no shot events", async ({ page }) => {
    const matchupId = "00000000-0000-0000-0000-000000000abc";
    await page.route("**/api/v1/matchups/*/event-heatmap", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          heat_grid: Array.from({ length: 10 }, () => Array(6).fill(0)),
          blocks: 0, steals: 0, fouls: 0, total_shots: 0, made_shots: 0,
          fg_pct: 0, event_count: 0,
        }),
      })
    );
    await page.route("**/api/v1/matchups/*", (route) => {
      // matchup detail (avoid matching the heatmap route, handled above)
      if (route.request().url().includes("event-heatmap")) return route.fallback();
      return route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ id: matchupId, name: "Test Matchup" }),
      });
    });
    await page.route("**/api/v1/matchups/*/live-keys**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await loginAs(page);
    await page.goto(`/game-tracker/${matchupId}/event-heatmap`);
    await expect(
      page.getByText(/Aún no hay eventos de tiro registrados/i)
    ).toBeVisible({ timeout: 10000 });
  });
});

test.describe("Phase A — box scores filter", () => {
  test("game option shows readable team names after selecting a season", async ({ page }) => {
    const seasonId = "00000000-0000-0000-0000-0000000000s1";
    await page.route("**/api/v1/seasons**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify([{ id: seasonId, name: "2024-25", year: "2024" }]) })
    );
    await page.route("**/api/v1/teams**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify([{ id: "t1", name: "Halcones" }, { id: "t2", name: "Pumas" }]) })
    );
    await page.route("**/api/v1/games**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ items: [
          { id: "g1", season_id: seasonId, home_team_name: "Halcones", away_team_name: "Pumas", game_date: "2024-12-15" },
        ], total: 1 }) })
    );

    await loginAs(page);
    await page.goto("/admin/box-scores");
    // Select the season → games load with readable labels.
    const seasonSelect = page.locator("select").first();
    await seasonSelect.selectOption(seasonId).catch(() => {});
    await expect(page.getByText(/Halcones vs Pumas/i).first()).toBeVisible({ timeout: 10000 });
  });
});
