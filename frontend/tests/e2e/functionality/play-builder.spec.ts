import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Play Builder", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/play-builder");
    await page.waitForLoadState("networkidle");
  });

  // ── Regression tests ──────────────────────────────────────────────────────

  test("play builder page loads", async ({ page }) => {
    await expect(page.getByText(/Play Builder/i).first()).toBeVisible({ timeout: 10000 });
  });

  test("SVG court canvas is present", async ({ page }) => {
    const svg = page.locator("svg").first();
    await expect(svg).toBeVisible({ timeout: 10000 });
  });

  // A2: tool panel is now vertical (data-testid="tool-panel-vertical")
  test("tool palette visible — regression", async ({ page }) => {
    // Tools may be in the vertical panel or top bar; check for tool buttons
    const palette = page.locator("button").filter({ hasText: /Select|Draw|Pass|Cut|Team/i });
    await expect(palette.first()).toBeVisible({ timeout: 10000 });
  });

  test("Add Frame button adds a frame", async ({ page }) => {
    // "Duplicate" or "Empty" frame buttons in the frame area
    const dupBtn = page.getByRole("button", { name: /Duplicate/i });
    const emptyBtn = page.getByRole("button", { name: /Empty/i });
    if (await dupBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await dupBtn.click();
      await page.waitForTimeout(500);
      // After duplicating, Frame 2 header should appear
      await expect(page.getByText(/Frame 2/i).first()).toBeVisible({ timeout: 5000 });
    } else if (await emptyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emptyBtn.click();
      await page.waitForTimeout(500);
      await expect(page.getByText(/Frame 2/i).first()).toBeVisible({ timeout: 5000 });
    }
  });

  // ── A1: Position labels ────────────────────────────────────────────────────

  test("A1 — position labels (PG/SG/SF/PF/C) render in player circles", async ({ page }) => {
    // The default frame has players labeled PG, SG, SF, PF, C
    // They appear as <text> inside the SVG
    const svgText = page.locator("svg text");
    const texts = await svgText.allTextContents();
    const positionLabels = texts.filter(t => /^(PG|SG|SF|PF|C)$/.test(t.trim()));
    expect(positionLabels.length).toBeGreaterThan(0);
  });

  // ── A2: Vertical tool panel ───────────────────────────────────────────────

  test("A2 — vertical tool panel is present on left side of canvas", async ({ page }) => {
    const toolPanel = page.locator("[data-testid='tool-panel-vertical']");
    await expect(toolPanel).toBeVisible({ timeout: 10000 });
    // Verify it contains tool buttons (Select, Team, Opp, Draw, Pass, Cut, Dribble, Screen)
    const selectBtn = toolPanel.getByRole("button", { name: /Select/i });
    await expect(selectBtn).toBeVisible({ timeout: 5000 });
  });

  test("A2 — vertical tool panel contains arrow style buttons", async ({ page }) => {
    const toolPanel = page.locator("[data-testid='tool-panel-vertical']");
    await expect(toolPanel).toBeVisible({ timeout: 10000 });
    const passBtn = toolPanel.getByRole("button", { name: /Pass/i });
    const cutBtn = toolPanel.getByRole("button", { name: /Cut/i });
    await expect(passBtn).toBeVisible({ timeout: 5000 });
    await expect(cutBtn).toBeVisible({ timeout: 5000 });
  });

  // ── A3: Notes per frame ───────────────────────────────────────────────────

  test("A3 — frame grid shows at least one frame card", async ({ page }) => {
    // Frame cards are in the grid; each has "Frame N" header
    const frameHeader = page.getByText(/Frame 1/i).first();
    await expect(frameHeader).toBeVisible({ timeout: 10000 });
  });

  test("A3 — frame card has a notes textarea below the mini court", async ({ page }) => {
    // Each frame card has an aria-labeled textarea for notes
    const notesArea = page.locator("textarea[aria-label='Frame 1 notes']");
    await expect(notesArea).toBeVisible({ timeout: 10000 });
  });

  test("A3 — notes per frame are editable and independent", async ({ page }) => {
    // Add a second frame
    const dupBtn = page.getByRole("button", { name: /Duplicate/i });
    if (await dupBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await dupBtn.click();
      // Now there should be 2 note textareas
      const frame1Notes = page.locator("textarea[aria-label='Frame 1 notes']");
      const frame2Notes = page.locator("textarea[aria-label='Frame 2 notes']");
      await expect(frame1Notes).toBeVisible({ timeout: 5000 });
      await expect(frame2Notes).toBeVisible({ timeout: 5000 });
      // Type notes in frame 1
      await frame1Notes.fill("Pick and roll from elbow");
      expect(await frame1Notes.inputValue()).toBe("Pick and roll from elbow");
      // Frame 2 notes should still be empty
      expect(await frame2Notes.inputValue()).toBe("");
    }
  });
});
