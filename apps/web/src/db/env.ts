import { existsSync } from "node:fs";

const ROOT_ENV_FILE = new URL("../../../../.env", import.meta.url);
let loaded = false;

/** Loads the repo-root .env once. Variables already set in the environment take precedence. */
export function loadRootEnv(): void {
  if (!loaded && existsSync(ROOT_ENV_FILE)) process.loadEnvFile(ROOT_ENV_FILE);
  loaded = true;
}

export function requireEnv(name: string): string {
  loadRootEnv();
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set (copy .env.example to .env at the repo root)`);
  return value;
}

/** Owner/migration connection string. */
export const databaseUrl = (): string => requireEnv("DATABASE_URL");

/** Least-privilege web connection string (D-035). */
export const appDatabaseUrl = (): string => requireEnv("APP_DATABASE_URL");
