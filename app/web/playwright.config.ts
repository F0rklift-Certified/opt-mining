import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e", timeout: 120_000, workers: 1, retries: 0,
  expect: { timeout: 90_000 },
  reporter: [["list"], ["json", { outputFile: "test-results/e2e-results.json" }]],
  use: { baseURL: process.env.E2E_WEB_URL ?? "http://localhost:3000",
    browserName: "chromium", headless: true, viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure", screenshot: "only-on-failure" },
});
