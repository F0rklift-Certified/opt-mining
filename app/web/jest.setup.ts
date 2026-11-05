/**
 * Shared Jest setup for the Opt-Mining Frontend_App tests (S3-01a).
 *
 * Registers the `@testing-library/jest-dom` custom matchers (e.g. `toBeInThe
 * Document`, `toHaveTextContent`) on every test run so all frontend test files
 * — this ticket's render test (6.5) and the later scope-guard (6.6) and smoke
 * (6.7) tests — share the same assertion vocabulary.
 */
import "@testing-library/jest-dom";

/*
 * jsdom does not implement a few browser APIs that `maplibre-gl` touches at
 * import/worker-setup time (S3-03a). Tests that exercise the map mock it, but
 * `AppShell`/`page` import `CellMap` (and therefore `maplibre-gl`) transitively,
 * so the module must at least load under jsdom even where the map never mounts.
 * These are inert stubs — no WebGL rendering happens in the suite.
 */
if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = () => "blob:jsdom-stub";
}
if (typeof URL.revokeObjectURL !== "function") {
  URL.revokeObjectURL = () => undefined;
}
