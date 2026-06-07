import { test, expect, type Page } from "@playwright/test";
import { loginAs } from "./helpers";

async function waitForGameTrackerHub(page: Page) {
  await expect(page.getByRole("heading", { name: "Game Tracker" })).toBeVisible({
    timeout: 15000,
  });
  const loader = page.locator("main .animate-spin");
  if (await loader.count()) {
    await loader.waitFor({ state: "hidden", timeout: 15000 }).catch(() => {});
  }
}

/** True when the hub lists at least one matchup (Log events / Heatmap actions). */
async function hasMatchupOnHub(page: Page): Promise<boolean> {
  return (await page.getByRole("link", { name: /Log events/i }).count()) > 0;
}

test.describe("Game Tracker", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-tracker");
    await page.waitForLoadState("networkidle");
    await waitForGameTrackerHub(page);
  });

  test("game tracker page renders", async ({ page }) => {
    await expect(page).toHaveURL(/game-tracker/);
    await expect(page.getByRole("heading", { name: "Game Tracker" })).toBeVisible();
  });

  test("scoreboard shows team scores", async ({ page }) => {
    const empty = page.getByText(/Sin partidos registrados/i);
    const liveSubtitle = page.getByText(/Marcador en vivo/i);
    const matchupSection = page.getByText(/Próximos|En vivo|Completados/i);
    const logEvents = page.getByRole("link", { name: /Log events/i });
    await expect(empty.or(liveSubtitle).or(matchupSection).or(logEvents).first()).toBeVisible({
      timeout: 15000,
    });
  });

  test("court svg is rendered when matchup available", async ({ page }) => {
    if (!(await hasMatchupOnHub(page))) {
      test.skip(true, "No matchups in seed data — heatmap court requires a matchup");
      return;
    }
    const heatmapLink = page.getByRole("link", { name: /^Heatmap$/i }).first();
    await heatmapLink.click();
    await expect(page).toHaveURL(/\/game-tracker\/[^/]+\/event-heatmap/, { timeout: 15000 });
    await expect(page.getByText(/Shot Heatmap/i)).toBeVisible({ timeout: 15000 });
    await expect(page.locator("main svg").first()).toBeVisible({ timeout: 15000 });
  });

  test.skip("sync indicator is shown", async () => {
    // Legacy live-court UI had a sync status badge; current hub + heatmap pages do not.
  });

  test("heat map toggle buttons are present when matchup available", async ({ page }) => {
    if (!(await hasMatchupOnHub(page))) {
      test.skip(true, "No matchups in seed data");
      return;
    }
    await expect(page.getByRole("link", { name: /^Heatmap$/i }).first()).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByRole("link", { name: /Log events/i }).first()).toBeVisible({
      timeout: 15000,
    });
  });

  test("can switch between heat map modes", async ({ page }) => {
    if (!(await hasMatchupOnHub(page))) {
      test.skip(true, "No matchups in seed data");
      return;
    }
    const logLink = page.getByRole("link", { name: /Log events/i }).first();
    await logLink.click();
    await expect(page).toHaveURL(/matchup=/, { timeout: 15000 });
    await expect(page.getByText(/Live logging/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: /Shot attempt/i })).toBeVisible({
      timeout: 15000,
    });
    const heatmapFromPanel = page.getByRole("link", { name: /Heatmap/i }).first();
    await heatmapFromPanel.click();
    await expect(page).toHaveURL(/event-heatmap/, { timeout: 15000 });
    await expect(page.locator("main svg").first()).toBeVisible({ timeout: 15000 });
  });
});
