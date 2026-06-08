import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testIgnore: process.env.INCLUDE_SCREENSHOTS ? [] : ["**/screenshots/**"],
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: "html",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:4000",
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
