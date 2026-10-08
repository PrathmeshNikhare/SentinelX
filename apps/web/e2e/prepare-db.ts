// Recreates the throwaway E2E database before the healthy server starts (run by playwright.config.ts).
import { drizzle } from "drizzle-orm/node-postgres";
import pg from "pg";
import { createAnalyst, enableAppRoleLogin } from "../src/db/admin.ts";
import { runMigrations } from "../src/db/migrate.ts";
import { seedReferenceData } from "../src/db/seed.ts";
import { E2E_ANALYST, E2E_DATABASE, e2eAppUrl, e2eOwnerUrl, ownerAdminUrl } from "./support.ts";

async function adminQuery(text: string): Promise<void> {
  const client = new pg.Client({ connectionString: ownerAdminUrl() });
  await client.connect();
  try {
    await client.query(text);
  } finally {
    await client.end();
  }
}

await adminQuery(`DROP DATABASE IF EXISTS ${E2E_DATABASE} WITH (FORCE)`);
await adminQuery(`CREATE DATABASE ${E2E_DATABASE}`);
await runMigrations(e2eOwnerUrl());

const pool = new pg.Pool({ connectionString: e2eOwnerUrl(), max: 1 });
try {
  const db = drizzle(pool);
  await seedReferenceData(db);
  await createAnalyst(db, E2E_ANALYST);
} finally {
  await pool.end();
}
await enableAppRoleLogin(e2eOwnerUrl(), e2eAppUrl());
console.log(JSON.stringify({ event: "e2e.database_ready", database: E2E_DATABASE }));
