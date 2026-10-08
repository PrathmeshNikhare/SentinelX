import { existsSync } from "node:fs";
import { resolve } from "node:path";
import type { NextConfig } from "next";

// The single .env lives at the repo root; variables already set (e.g. by Playwright) take precedence.
const rootEnv = resolve(process.cwd(), "../../.env");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // pg is a Node-only driver; keep it out of the server bundle.
  serverExternalPackages: ["pg"],
};

export default nextConfig;
