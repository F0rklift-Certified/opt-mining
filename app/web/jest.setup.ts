/**
 * Shared Jest setup for the Opt-Mining Frontend_App tests (S3-01a).
 *
 * Registers the `@testing-library/jest-dom` custom matchers (e.g. `toBeInThe
 * Document`, `toHaveTextContent`) on every test run so all frontend test files
 * — this ticket's render test (6.5) and the later scope-guard (6.6) and smoke
 * (6.7) tests — share the same assertion vocabulary.
 */
import "@testing-library/jest-dom";
