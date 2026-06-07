import { test, expect } from "@playwright/test";

const PROTECTED_ROUTES = [
  "/",
  "/scouting",
  "/game-day",
  "/game-tracker",
  "/play-builder",
  "/games",
  "/training",
  "/matchups",
  "/admin",
];

test.describe("Auth Gates", () => {
  for (const route of PROTECTED_ROUTES) {
    test(`${route} redirects to /login when unauthenticated`, async ({ page }) => {
      // Clear cookies
      await page.context().clearCookies();
      await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
      await page.goto(route, { waitUntil: "domcontentloaded" });
      await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
      await expect(page).toHaveURL(/\/login/, { timeout: 15000 });
      await expect(page).toHaveURL(/\/login/);
    });
  }

  test("valid login redirects to dashboard", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/login");
    await page.fill("input[type=email], input[name=email]", process.env.TEST_EMAIL ?? "admin@test.com");
    await page.fill("input[type=password], input[name=password]", process.env.TEST_PASSWORD ?? "Test1234!");
    await page.click("button[type=submit]");
    await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15000 });
    expect(page.url()).not.toContain("/login");
  });
});
