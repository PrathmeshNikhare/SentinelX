import { existsSync } from "node:fs";
import { resolve } from "node:path";
import type { NextConfig } from "next";

// The single .env lives at the repo root; variables already set (e.g. by Playwright) take precedence.
const rootEnv = resolve(process.cwd(), "../../.env");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

// Security headers (D-076), from the Next.js "Without Nonces" CSP guide. React needs 'unsafe-eval' in development only.
// ponytail: scripts allow 'unsafe-inline' (Next.js hydration scripts); upgrade to nonces or SRI if the console is
// ever exposed beyond the analyst's machine. No upgrade-insecure-requests: the console is served over local HTTP.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Node-only drivers (pg, native librdkafka binding); keep them out of the server bundle.
  serverExternalPackages: ["pg", "@confluentinc/kafka-javascript"],
  headers: async () => [{ source: "/(.*)", headers: SECURITY_HEADERS }],
};

export default nextConfig;
