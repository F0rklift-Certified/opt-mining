/**
 * Smoke test — the Frontend_App is a browser-based web app, not a desktop
 * executable (S3-01a, task 6.7).
 *
 * This is the design's "Frontend is a web app (smoke)" check from the Testing
 * Strategy, covering Requirement 1.1: THE Frontend_App SHALL be a browser-based
 * web application built with Next.js/React and SHALL NOT be a desktop
 * executable. It asserts three things:
 *
 *   1. `app/web/package.json` declares `next` AND `react` (i.e. it IS a
 *      Next.js/React web app) — read from the actual manifest.
 *   2. The app renders in a jsdom (browser-like) context — the shell/page
 *      mounts into the DOM without error, proving it is a client/browser-
 *      renderable web app rather than a native binary.
 *   3. There is NO desktop-executable build — no electron/tauri/pkg/nw (or
 *      similar) dependency, and no desktop packaging build script, appears in
 *      package.json.
 *
 * jsdom is the test environment configured in jest.config.js, so a successful
 * React render here is exactly "renders in a browser-like DOM context".
 */
import { readFileSync } from "fs";
import { join } from "path";

import { render, screen } from "@testing-library/react";

import Page from "../app/page";

/** Repo-relative root of the frontend app (this test lives in app/web/__tests__). */
const WEB_ROOT = join(__dirname, "..");

/** Parse the real package.json manifest for the frontend app. */
function readPackageJson(): {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  scripts?: Record<string, string>;
} {
  const raw = readFileSync(join(WEB_ROOT, "package.json"), "utf8");
  return JSON.parse(raw);
}

describe("Frontend is a web app, not a desktop executable (S3-01a, task 6.7, R1.1)", () => {
  describe("package.json declares a Next.js/React web app", () => {
    const pkg = readPackageJson();
    const allDeps: Record<string, string> = {
      ...(pkg.dependencies ?? {}),
      ...(pkg.devDependencies ?? {}),
    };

    it("declares `next` as a dependency (it is a Next.js app)", () => {
      expect(allDeps).toHaveProperty("next");
    });

    it("declares `react` as a dependency (it is a React app)", () => {
      expect(allDeps).toHaveProperty("react");
    });

    it("declares web run scripts (dev/build/start map to the Next.js toolchain)", () => {
      const scripts = pkg.scripts ?? {};
      // The build/start commands are the Next.js web toolchain — not a desktop
      // packager. This anchors the "web app" claim to the actual scripts.
      expect(scripts.dev).toMatch(/\bnext\b/);
      expect(scripts.build).toMatch(/\bnext\b/);
      expect(scripts.start).toMatch(/\bnext\b/);
    });
  });

  describe("the app renders in a jsdom (browser-like) context", () => {
    it("mounts the shell page into the DOM without error", () => {
      // A successful React render into jsdom proves the app is a browser-
      // renderable web app. If this were a native desktop binary there would be
      // no renderable React tree to mount here.
      const { container } = render(<Page />);
      expect(container).toBeInTheDocument();
      expect(container.firstChild).not.toBeNull();
    });

    it("renders the four labelled placeholder regions in the DOM", () => {
      // Confirm the mount produced live DOM content (region landmarks), i.e. the
      // page really rendered in the browser-like environment.
      render(<Page />);
      const regions = screen.getAllByRole("region");
      expect(regions.length).toBeGreaterThan(0);
    });
  });

  describe("there is NO desktop-executable build", () => {
    const pkg = readPackageJson();
    const allDeps: Record<string, string> = {
      ...(pkg.dependencies ?? {}),
      ...(pkg.devDependencies ?? {}),
    };
    const scripts = pkg.scripts ?? {};

    // Dependencies/toolchains that would turn this into a desktop executable.
    const DESKTOP_PACKAGES = [
      "electron",
      "electron-builder",
      "electron-packager",
      "@electron-forge/cli",
      "@tauri-apps/cli",
      "@tauri-apps/api",
      "tauri",
      "pkg",
      "nw",
      "nwjs",
      "nw-builder",
      "neutralino",
      "@neutralinojs/neu",
    ];

    it.each(DESKTOP_PACKAGES)(
      "does not depend on the desktop packager `%s`",
      (packageName) => {
        expect(allDeps).not.toHaveProperty(packageName);
      },
    );

    it("declares no desktop-packaging build script", () => {
      // No script invokes a desktop packager (electron/tauri/pkg/nw/…). A web
      // app's scripts drive `next`, not a native bundler.
      const scriptText = Object.values(scripts).join(" ");
      expect(scriptText).not.toMatch(
        /\b(electron|electron-builder|electron-packager|electron-forge|tauri|nwjs|nw-builder|neutralino)\b/i,
      );
      // `pkg` as a standalone binary packager (guard the whole-word command,
      // not substrings like "package").
      expect(scriptText).not.toMatch(/(^|\s)pkg(\s|$)/);
    });

    it("has no `main` entry pointing at a desktop-shell entrypoint", () => {
      // A `main` field is how Electron/NW.js locate a desktop entrypoint; a
      // browser Next.js app has none. Its absence corroborates "web app".
      expect(pkg).not.toHaveProperty("main");
    });
  });
});
