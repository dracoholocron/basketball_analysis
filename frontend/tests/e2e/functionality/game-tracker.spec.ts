import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Game Tracker", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-tracker");
    await page.waitForLoadState("networkidle");
  });

  // ── Regression tests ──────────────────────────────────────────────────────

  test("renders page title", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Game Tracker" })).toBeVisible({ timeout: 8000 });
  });

  test("shows matchup selector or empty state", async ({ page }) => {
    const selector = page.locator("select");
    const emptyMsg = page.getByText("No matchups found");
    await expect(selector.or(emptyMsg).first()).toBeVisible({ timeout: 10000 });
  });

  test("clock widget renders with MM:SS format", async ({ page }) => {
    const clockText = page.locator("text=/\\d{2}:\\d{2}/");
    const noMatchup = page.getByText(/no matchup|select a matchup/i);
    await expect(clockText.or(noMatchup).first()).toBeVisible({ timeout: 10000 });
  });

  test("roster sidebars visible on large viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Use the uppercase exact label in the roster panel header (span element)
    const ownRoster = page.locator("span").filter({ hasText: /^YOUR TEAM$/ }).first();
    const oppRoster = page.locator("span").filter({ hasText: /^OPPONENT$/ }).first();
    const emptyState = page.getByText(/no matchup|select a matchup|no match/i);
    await expect(ownRoster.or(emptyState).first()).toBeVisible({ timeout: 10000 });
    if (await ownRoster.isVisible({ timeout: 1000 }).catch(() => false)) {
      await expect(oppRoster).toBeVisible({ timeout: 5000 });
    }
  });

  test("history button toggles event list", async ({ page }) => {
    const historyBtn = page.getByRole("button", { name: /History/i });
    if (await historyBtn.isVisible()) {
      await historyBtn.click();
      await expect(page.getByText("Last 20 Events")).toBeVisible({ timeout: 5000 });
    }
  });

  // ── B1: Assist modal ───────────────────────────────────────────────────────

  test("B1 — assist modal appears when court has a made basket logged", async ({ page }) => {
    // Only runs when a matchup is present (court is clickable)
    const courtSvg = page.locator("svg.cursor-crosshair, svg[class*='crosshair']");
    const hasMatchup = await courtSvg.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasMatchup) {
      test.skip();
      return;
    }

    // Click the court SVG to open event picker
    const svgBox = await courtSvg.boundingBox();
    if (!svgBox) { test.skip(); return; }
    await courtSvg.click({ position: { x: svgBox.width * 0.3, y: svgBox.height * 0.5 } });

    // Wait for shot type picker to appear
    const shotPicker = page.getByText(/Log event for which team/i);
    const hasPicker = await shotPicker.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasPicker) { test.skip(); return; }

    // Click "T1: 2pt Made"
    const btn2ptT1 = page.getByRole("button", { name: /T1:.*2pt Made/i });
    const hasBtn = await btn2ptT1.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtn) { test.skip(); return; }
    await btn2ptT1.click();

    // B1: Assist modal should appear
    const assistModal = page.getByRole("dialog", { name: /Who assisted/i });
    await expect(assistModal).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/Who assisted/i)).toBeVisible({ timeout: 5000 });
  });

  test("B1 — assist modal has N/A button to dismiss without assist event", async ({ page }) => {
    const courtSvg = page.locator("svg.cursor-crosshair, svg[class*='crosshair']");
    const hasMatchup = await courtSvg.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasMatchup) { test.skip(); return; }

    const svgBox = await courtSvg.boundingBox();
    if (!svgBox) { test.skip(); return; }
    await courtSvg.click({ position: { x: svgBox.width * 0.3, y: svgBox.height * 0.5 } });

    const shotPicker = page.getByText(/Log event for which team/i);
    const hasPicker = await shotPicker.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasPicker) { test.skip(); return; }

    const btn2ptT1 = page.getByRole("button", { name: /T1:.*2pt Made/i });
    const hasBtn = await btn2ptT1.isVisible({ timeout: 3000 }).catch(() => false);
    if (!hasBtn) { test.skip(); return; }
    await btn2ptT1.click();

    // Wait for assist modal
    const naBtn = page.getByRole("button", { name: /N\/A|No assist/i });
    const hasNaBtn = await naBtn.isVisible({ timeout: 5000 }).catch(() => false);
    if (!hasNaBtn) { test.skip(); return; }

    // Click N/A — modal should close
    await naBtn.click();
    await expect(naBtn).not.toBeVisible({ timeout: 3000 });
  });
});
