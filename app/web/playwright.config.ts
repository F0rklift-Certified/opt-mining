/**
 * Playwright configuration for the browser end-to-end tests (S4-09a).
 *
 * The tests drive an ALREADY RUNNING stack (API + web), the same one a user
 * starts with `docker compose -f docker-compose.yml up --build` or the
 * non-Docker commands in app/README.md. Point them elsewhere with
 * E2E_BASE_URL. Jest does not collect `e2e/` (see jest.config.js testMatch).
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // A cold run store materialises the first Run (~10–30 s), so allow headroom.
  timeout: 180_000,
  expect: { timeout: 90_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
