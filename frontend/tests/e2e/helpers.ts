/**
 * Shared test helpers for E2E tests.
 */
import { Page } from "@playwright/test";

const ADMIN_EMAIL = process.env.TEST_EMAIL ?? "admin@test.com";
const ADMIN_PASS = process.env.TEST_PASSWORD ?? "admin123";

export async function loginAs(page: Page, email = ADMIN_EMAIL, password = ADMIN_PASS) {
  await page.goto("/login");
  await page.fill("input[type=email], input[name=email]", email);
  await page.fill("input[type=password], input[name=password]", password);
  await page.click("button[type=submit]");
  // Accept any non-login URL as success (could be /, /game-day, /dashboard, etc.)
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 10000 });
}
