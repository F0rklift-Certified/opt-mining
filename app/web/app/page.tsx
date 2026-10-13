/**
 * App Router home page for the Opt-Mining Frontend_App.
 *
 * This is the single page of the MVP shell. It renders the `AppShell`, which
 * preserves the four fixed shell regions and populates them through the shared
 * S3-01b decision-service client. This page holds no decision logic.
 */
import AppShell from "./shell/AppShell";

export default function Page(): JSX.Element {
  return <AppShell />;
}
