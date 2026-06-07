import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/games", label: "Games" },
  { href: "/scouting", label: "Scouting" },
  { href: "/game-day", label: "Game Day" },
  { href: "/game-tracker", label: "Game Tracker" },
  { href: "/play-builder", label: "Play Builder" },
  { href: "/training", label: "Training" },
  { href: "/matchups", label: "Matchup Workspace" },
  { href: "/admin", label: "Settings" },
];

test.describe("Sidebar Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  for (const item of NAV_ITEMS) {
    test(`Clicking "${item.label}" navigates to ${item.href}`, async ({ page }) => {
      await page.goto("/");
      const link = page.getByRole("link", { name: new RegExp(item.label, "i") }).first();
      await expect(link).toBeVisible({ timeout: 10000 });
      await link.click();
      await page.waitForURL(new RegExp(item.href === "/" ? "\\/$" : item.href), { timeout: 10000 });
      expect(page.url()).toContain(item.href === "/" ? "" : item.href);
    });
  }
});
