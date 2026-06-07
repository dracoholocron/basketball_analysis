import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("Matchup Workspace Tabs", () => {
  test("each tab updates URL query param", async ({ page }) => {
    await loginAs(page);
    await page.goto("/matchups");

    const matchupLink = page.locator(".divide-y a").first();
    if (!await matchupLink.isVisible({ timeout: 5000 })) {
      test.skip(); return;
    }
    await matchupLink.click();
    await page.waitForURL(/\/matchups\/.+/, { timeout: 10000 });

    const tabs = ["scouting", "plays", "tracker", "notes"];
    for (const tab of tabs) {
      const tabBtn = page.getByRole("button", { name: new RegExp(tab, "i") });
      if (await tabBtn.isVisible({ timeout: 3000 })) {
        await tabBtn.click();
        await expect(page.url()).toContain(`tab=${tab}`);
      }
    }
  });

  test("browser back restores previous tab", async ({ page }) => {
    await loginAs(page);
    await page.goto("/matchups");

    const matchupLink = page.locator(".divide-y a").first();
    if (!await matchupLink.isVisible({ timeout: 5000 })) {
      test.skip(); return;
    }
    await matchupLink.click();
    await page.waitForURL(/\/matchups\/.+/, { timeout: 10000 });

    const playsTab = page.getByRole("button", { name: /Plays/i });
    if (await playsTab.isVisible({ timeout: 3000 })) {
      await playsTab.click();
      expect(page.url()).toContain("tab=plays");

      await page.goBack();
      expect(page.url()).not.toContain("tab=plays");
    }
  });
});
