import { defineConfig, devices } from "@playwright/test";

// Defaults to a dev server on :3100; set E2E_BASE_URL to run against an already
// running app instead (e.g. the backend serving the static build on :8000).
const baseURL = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  // The app writes to one shared database, so tests must not run concurrently.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: baseURL || "http://localhost:3100",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: baseURL
    ? undefined
    : {
        command: "npm run dev -- --port 3100",
        url: "http://localhost:3100",
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
});
