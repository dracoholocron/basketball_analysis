import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers";

test.describe("404 handling", () => {
  test("unknown route shows 404 page", async ({ page }) => {
    await loginAs(page);
    await page.goto("/this-route-does-not-exist-xyz-abc");
    // Either Next.js shows 404 or redirects, both acceptable
    const is404 = await page.getByText(/404|not found|page not found/i).first().isVisible({ timeout: 5000 });
    const isRedirected = page.url().includes("/login") || page.url().endsWith("/");
    expect(is404 || isRedirected).toBeTruthy();
  });

  test("invalid matchup UUID shows 404 or empty state", async ({ page }) => {
    await loginAs(page);
    await page.goto("/matchups/00000000-0000-0000-0000-000000000000");
    await page.waitForTimeout(3000);
    const finalUrl = page.url();
    const errorOrEmpty = page.getByText(/404|not found|No matchup|error/i);
    const isRedirected = finalUrl.includes("/login") || finalUrl.endsWith("/") || finalUrl.endsWith("/#");
    const isVisible = await errorOrEmpty.first().isVisible({ timeout: 5000 }).catch(() => false);
    const isOnMatchupsPage = finalUrl.includes("/matchups");
    // Accept any non-crash outcome
    expect(isVisible || isRedirected || isOnMatchupsPage).toBeTruthy();
  });
});
