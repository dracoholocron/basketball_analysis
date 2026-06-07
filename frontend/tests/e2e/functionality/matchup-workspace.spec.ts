import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Matchup Workspace", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
    await page.goto("/matchups");
  });

  test("renders Matchup Workspace page", async ({ page }) => {
    await expect(page.getByText(/Matchup Workspace/i).first()).toBeVisible({ timeout: 10000 });
  });

  test("shows empty state or matchup list", async ({ page }) => {
    const list = page.locator(".divide-y a");
    const empty = page.getByText(/No matchups yet/i);
    await expect(list.first().or(empty).first()).toBeVisible({ timeout: 10000 });
  });
});

test.describe("Matchup Workspace Detail", () => {
  test("tabs navigate and change URL", async ({ page }) => {
    await loginAs(page);
    await page.goto("/matchups");

    // If matchups exist, click the first one
    const link = page.locator(".divide-y a").first();
    if (await link.isVisible({ timeout: 5000 })) {
      await link.click();
      await page.waitForURL(/\/matchups\/.+/, { timeout: 10000 });

      // Click each tab
      for (const tabLabel of ["Scouting", "Plays", "Notes"]) {
        const tab = page.getByRole("button", { name: new RegExp(tabLabel, "i") });
        if (await tab.isVisible()) {
          await tab.click();
          await expect(page.url()).toContain(`tab=${tabLabel.toLowerCase()}`);
        }
      }
    }
  });
});
