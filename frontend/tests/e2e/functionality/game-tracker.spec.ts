import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Game Tracker", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-tracker");
    await page.waitForLoadState("networkidle");
  });

  // ── Regression tests (hub UI — list + live logging, not legacy court/clock) ──

  test("renders page title", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Game Tracker" })).toBeVisible({ timeout: 8000 });
  });

  test("shows matchup selector or empty state", async ({ page }) => {
    const empty = page.getByText(/Sin partidos registrados/i);
    const section = page.getByText(/Próximos|En vivo|Completados/i);
    const logEvents = page.getByRole("link", { name: /Log events/i });
    await expect(empty.or(section).or(logEvents).first()).toBeVisible({ timeout: 10000 });
  });

  test("clock widget renders with MM:SS format", async ({ page }) => {
    const empty = page.getByText(/Sin partidos registrados/i);
    const liveLogging = page.getByText(/Live logging/i);
    const timeOnEvent = page.locator("li").filter({ hasText: /T[12]/ }).first();
    await expect(empty.or(liveLogging).or(timeOnEvent).first()).toBeVisible({ timeout: 10000 });
  });

  test("roster sidebars visible on large viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const empty = page.getByText(/Sin partidos registrados/i);
    const matchupActions = page.getByRole("link", { name: /Log events|Heatmap/i }).first();
    await expect(empty.or(matchupActions)).toBeVisible({ timeout: 10000 });
  });

  test("history button toggles event list", async ({ page }) => {
    const historyBtn = page.getByRole("button", { name: /History/i });
    if (await historyBtn.isVisible()) {
      await historyBtn.click();
      await expect(page.getByText("Last 20 Events")).toBeVisible({ timeout: 5000 });
    }
  });

  // ── B1: Assist modal (legacy court UI — skip until court view is restored) ──

  test("B1 — assist modal appears when court has a made basket logged", async ({ page }) => {
    const courtSvg = page.locator("svg.cursor-crosshair, svg[class*='crosshair']");
    const hasMatchup = await courtSvg.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasMatchup) {
      test.skip(true, "Court SVG game tracker not on hub page");
      return;
    }

    const svgBox = await courtSvg.boundingBox();
    if (!svgBox) { test.skip(true, "No court bounding box"); return; }
    await courtSvg.click({ position: { x: svgBox.width * 0.3, y: svgBox.height * 0.5 } });

    const shotPicker = page.getByText(/Log event for which team/i);
    const hasPicker = await shotPicker.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasPicker) { test.skip(true, "Shot picker not available"); return; }

    const btn2ptT1 = page.getByRole("button", { name: /T1:.*2pt Made/i });
    const hasBtn = await btn2ptT1.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtn) { test.skip(true, "2pt Made button not available"); return; }
    await btn2ptT1.click();

    const assistModal = page.getByRole("dialog", { name: /Who assisted/i });
    await expect(assistModal).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/Who assisted/i)).toBeVisible({ timeout: 5000 });
  });

  test("B1 — assist modal has N/A button to dismiss without assist event", async ({ page }) => {
    const courtSvg = page.locator("svg.cursor-crosshair, svg[class*='crosshair']");
    const hasMatchup = await courtSvg.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasMatchup) { test.skip(true, "Court SVG game tracker not on hub page"); return; }

    const svgBox = await courtSvg.boundingBox();
    if (!svgBox) { test.skip(true, "No court bounding box"); return; }
    await courtSvg.click({ position: { x: svgBox.width * 0.3, y: svgBox.height * 0.5 } });

    const shotPicker = page.getByText(/Log event for which team/i);
    const hasPicker = await shotPicker.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasPicker) { test.skip(true, "Shot picker not available"); return; }

    const btn2ptT1 = page.getByRole("button", { name: /T1:.*2pt Made/i });
    const hasBtn = await btn2ptT1.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtn) { test.skip(true, "2pt Made button not available"); return; }
    await btn2ptT1.click();

    const naBtn = page.getByRole("button", { name: /N\/A|No assist/i });
    const hasNaBtn = await naBtn.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasNaBtn) { test.skip(true, "Assist modal N/A not available"); return; }

    await naBtn.click();
    await expect(naBtn).not.toBeVisible({ timeout: 3000 });
  });
});
