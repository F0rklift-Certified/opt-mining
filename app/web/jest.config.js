/**
 * Jest configuration for the Opt-Mining Frontend_App (S3-01a).
 *
 * Uses `next/jest`, the standard Next.js test transform, so Jest picks up the
 * project's `tsconfig.json`, compiles TS/TSX and handles CSS/asset imports the
 * same way the Next.js build does. This keeps the test toolchain aligned with
 * the app build with minimal, pinned additions.
 *
 * The config is deliberately generic (jsdom environment, shared setup file, a
 * `<rootDir>/**` test match) so later frontend test tasks — the static
 * scope-guard test (6.6) and the web-app smoke test (6.7) — slot in without
 * further config changes.
 *
 * @type {import('jest').Config}
 */
const nextJest = require("next/jest");

const createJestConfig = nextJest({
  // Load next.config.js and .env files from the app directory.
  dir: "./",
});

/** @type {import('jest').Config} */
const customJestConfig = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  // Co-located tests under app/ plus any top-level __tests__ directory.
  testMatch: [
    "<rootDir>/app/**/*.test.{ts,tsx}",
    "<rootDir>/__tests__/**/*.test.{ts,tsx}",
  ],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
};

module.exports = createJestConfig(customJestConfig);
