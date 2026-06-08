/**
 * Shared test helpers for E2E tests.
 */
import { Page } from "@playwright/test";

const ADMIN_EMAIL = process.env.TEST_EMAIL ?? "admin@test.com";
const ADMIN_PASS = process.env.TEST_PASSWORD ?? "Test1234!";

export async function loginAs(page: Page, email = ADMIN_EMAIL, password = ADMIN_PASS) {
  // Mock the auth token endpoint so login always succeeds in E2E without
  // depending on a live API or valid credentials.
  await page.route("**/api/v1/auth/token", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ access_token: "fake-e2e-token", token_type: "bearer" }),
    })
  );
  await page.goto("/login");
  await page.fill("input[type=email], input[name=email]", email);
  await page.fill("input[type=password], input[name=password]", password);
  await page.click("button[type=submit]");
  // Accept any non-login URL as success (could be /, /game-day, /dashboard, etc.)
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 10000 });
}
