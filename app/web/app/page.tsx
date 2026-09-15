/**
 * App Router home page for the Opt-Mining Frontend_App (S3-01a, task 6.4).
 *
 * This is the single page of the MVP shell. It renders the `AppShell`, which
 * lays out the four fixed `PlaceholderRegion`s (Requirements 3.1–3.4). It holds
 * no decision logic and makes no requests (Requirements 3.5, 8.1, 8.3).
 */
import AppShell from "./shell/AppShell";

export default function Page(): JSX.Element {
  return <AppShell />;
}
