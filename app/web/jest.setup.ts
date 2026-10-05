/**
 * Shared Jest setup for the Opt-Mining Frontend_App tests (S3-01a).
 *
 * Registers the `@testing-library/jest-dom` custom matchers (e.g. `toBeInThe
 * Document`, `toHaveTextContent`) on every test run so all frontend test files
 * — this ticket's render test (6.5) and the later scope-guard (6.6) and smoke
 * (6.7) tests — share the same assertion vocabulary.
 */
import "@testing-library/jest-dom";

// jsdom has no pixel canvas. Drawing is verified in real Chromium E2E; unit
// tests use a context spy, so map selection is still exercised without noisy
// "not implemented" errors or installing an unrelated native canvas library.
if (typeof HTMLCanvasElement !== "undefined") Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  value: jest.fn(() => ({
    clearRect: jest.fn(), fillRect: jest.fn(), beginPath: jest.fn(),
    moveTo: jest.fn(), lineTo: jest.fn(), closePath: jest.fn(),
    fill: jest.fn(), stroke: jest.fn(), strokeRect: jest.fn(),
  })),
});
