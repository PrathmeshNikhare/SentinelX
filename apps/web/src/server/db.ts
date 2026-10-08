import "server-only";
import { drizzle, type NodePgDatabase } from "drizzle-orm/node-postgres";
import pg from "pg";

let database: NodePgDatabase | undefined;

/** Web connection as the least-privilege sentinelx_app role (D-035). Created lazily on first use. */
export function db(): NodePgDatabase {
  // next.config.ts loads the repo-root .env. Do not import src/db/env.ts here: its `new URL(".env", import.meta.url)`
  // is treated by the bundler as an asset reference and would pull .env into the build.
  const url = process.env.APP_DATABASE_URL;
  if (!url) throw new Error("APP_DATABASE_URL is not set (copy .env.example to .env at the repo root)");
  database ??= drizzle(new pg.Pool({ connectionString: url, max: 10, connectionTimeoutMillis: 3_000 }));
  return database;
}
