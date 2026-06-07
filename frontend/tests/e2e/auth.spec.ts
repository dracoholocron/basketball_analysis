import { test, expect } from "@playwright/test";

const ADMIN_EMAIL = process.env.TEST_EMAIL ?? "admin@test.com";
const ADMIN_PASS = process.env.TEST_PASSWORD ?? "admin123";

test.describe("Authentication", () => {
  test("login page renders", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("input[type=email], input[name=email]")).toBeVisible();
    await expect(page.locator("input[type=password], input[name=password]")).toBeVisible();
  });

  test("login with correct credentials redirects to dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.fill("input[type=email], input[name=email]", ADMIN_EMAIL);
    await page.fill("input[type=password], input[name=password]", ADMIN_PASS);
    await page.click("button[type=submit]");
    await expect(page).toHaveURL(/\/$|dashboard/, { timeout: 10000 });
  });

  test("login with wrong password shows error", async ({ page }) => {
    await page.goto("/login");
    await page.fill("input[type=email], input[name=email]", ADMIN_EMAIL);
    await page.fill("input[type=password], input[name=password]", "wrongpassword");
    await page.click("button[type=submit]");
    // Should stay on login or show error
    await page.waitForTimeout(2000);
    const url = page.url();
    const hasError = await page.locator("text=/error|incorrect|invalid|failed/i").isVisible().catch(() => false);
    expect(url.includes("/login") || hasError).toBeTruthy();
  });

  test("protected route redirects to login when unauthenticated", async ({ page }) => {
    // Clear cookies to ensure unauthenticated state
    await page.context().clearCookies();
    await page.goto("/");
    await expect(page).toHaveURL(/login/, { timeout: 10000 });
  });
});
