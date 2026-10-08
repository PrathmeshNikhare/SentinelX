// Shared E2E settings (D-037). Used by playwright.config.ts, prepare-db.ts, global-teardown.ts and the specs.
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const rootEnv = resolve(process.cwd(), "../../.env");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set (copy .env.example to .env at the repo root)`);
  return value;
}

function withDatabase(url: string, database: string): string {
  const parsed = new URL(url);
  parsed.pathname = `/${database}`;
  return parsed.toString();
}

export const E2E_DATABASE = "sentinelx_e2e";
export const HEALTHY_URL = "http://localhost:3100";
export const DEGRADED_URL = "http://localhost:3101";

/** Valid only for the E2E servers (both get it via playwright.config.ts). */
export const E2E_INGEST_TOKEN = "e2e-ingest-token-0123456789abcdefghijklmnop";
/** Isolated topic: E2E traffic must never reach the worker's `security-events` topic. */
export const E2E_EVENTS_TOPIC = "security-events-e2e";
export const kafkaBrokers = (): string => required("KAFKA_BROKERS");

export const E2E_ANALYST = {
  email: "e2e.analyst@sentinelx.local",
  name: "E2E Analyst",
  password: "e2e-analyst-password-2026",
} as const;

/** Owner connection to the main database; used to create and drop the E2E database. */
export const ownerAdminUrl = (): string => required("DATABASE_URL");
export const e2eOwnerUrl = (): string => withDatabase(required("DATABASE_URL"), E2E_DATABASE);
export const e2eAppUrl = (): string => withDatabase(required("APP_DATABASE_URL"), E2E_DATABASE);

/** Same credentials, closed port: drives the degraded server. */
export function unreachableAppUrl(): string {
  const parsed = new URL(required("APP_DATABASE_URL"));
  parsed.port = "1";
  return parsed.toString();
}
