import { existsSync } from "node:fs";

const ROOT_ENV_FILE = new URL("../../../../.env", import.meta.url);

/** Owner/migration connection string. Loads the repo-root .env when DATABASE_URL is not already set. */
export function databaseUrl(): string {
  if (!process.env.DATABASE_URL && existsSync(ROOT_ENV_FILE)) {
    process.loadEnvFile(ROOT_ENV_FILE);
  }
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error("DATABASE_URL is not set (copy .env.example to .env at the repo root)");
  }
  return url;
}
