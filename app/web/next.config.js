/**
 * Next.js configuration for the Opt-Mining Frontend_App (S3-01a).
 *
 * Boundary rule (Requirement 4.3): the backend Service_URL is read ONLY from the
 * `NEXT_PUBLIC_API_BASE_URL` environment variable. Next.js automatically inlines
 * any `NEXT_PUBLIC_*` variable from the environment at build/runtime, so it is
 * intentionally NOT re-declared here — and, critically, NO host address is
 * hard-coded anywhere in this config or elsewhere in the frontend source.
 *
 * @type {import('next').NextConfig}
 */
const nextConfig = {
  reactStrictMode: true,
};

module.exports = nextConfig;
