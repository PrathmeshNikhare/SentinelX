import { existsSync } from "node:fs";
import { resolve } from "node:path";
import type { NextConfig } from "next";

// The single .env lives at the repo root; variables already set (e.g. by Playwright) take precedence.
const rootEnv = resolve(process.cwd(), "../../.env");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Node-only drivers (pg, native librdkafka binding); keep them out of the server bundle.
  serverExternalPackages: ["pg", "@confluentinc/kafka-javascript"],
};

export default nextConfig;
