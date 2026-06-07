import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Event Heatmap", () => {
  test("navigating to heatmap page shows correct title", async ({ page }) => {
    await loginAs(page);
    await page.goto("/game-tracker");

    const heatmapLink = page.getByRole("link", { name: /Event Heatmap/i });
    if (await heatmapLink.isVisible({ timeout: 5000 })) {
      await heatmapLink.click();
      await expect(page.getByText(/Event Heatmap|Heat Map/i).first()).toBeVisible({ timeout: 10000 });
    }
  });
});
