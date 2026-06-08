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
      // Clear cookies — middleware checks the cookie server-side and redirects
      await page.context().clearCookies();
      // Navigate and wait for the final page (after the server-side redirect) to load
      await page.goto(route, { waitUntil: "load" });
      await expect(page).toHaveURL(/\/login/, { timeout: 15000 });
    });
  }

  test("valid login redirects to dashboard", async ({ page }) => {
    await page.route("**/api/v1/auth/token", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ access_token: "fake-e2e-token", token_type: "bearer" }),
      })
    );
    await page.context().clearCookies();
    await page.goto("/login");
    await page.fill("input[type=email], input[name=email]", process.env.TEST_EMAIL ?? "admin@test.com");
    await page.fill("input[type=password], input[name=password]", process.env.TEST_PASSWORD ?? "Test1234!");
    await page.click("button[type=submit]");
    await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15000 });
    expect(page.url()).not.toContain("/login");
  });
});
