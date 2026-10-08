// Usage (from apps/web):
//   npm run db:migrate | npm run db:seed | npm run db:roles
//   ANALYST_PASSWORD=... npm run analyst:create -- <email> "<name>"
// Logs one JSON line per run; never logs connection strings or passwords.
import { drizzle, type NodePgDatabase } from "drizzle-orm/node-postgres";
import pg from "pg";
import { AI_TOOLS_ROLE, APP_ROLE, createAnalyst, enableRoleLogin } from "./admin.ts";
import { aiToolsDatabaseUrl, appDatabaseUrl, databaseUrl, requireEnv } from "./env.ts";
import { runMigrations } from "./migrate.ts";
import { seedReferenceData } from "./seed.ts";

const log = (fields: Record<string, unknown>) =>
  console.log(JSON.stringify({ ts: new Date().toISOString(), ...fields }));

async function withOwnerDb<T>(fn: (db: NodePgDatabase) => Promise<T>): Promise<T> {
  const pool = new pg.Pool({ connectionString: databaseUrl(), max: 1 });
  try {
    return await fn(drizzle(pool));
  } finally {
    await pool.end();
  }
}

async function main([command, ...args]: string[]): Promise<void> {
  switch (command) {
    case "migrate":
      await runMigrations(databaseUrl());
      log({ event: "db.migrate", status: "ok" });
      return;
    case "seed": {
      const counts = await withOwnerDb((db) => seedReferenceData(db));
      log({ event: "db.seed", status: "ok", ...counts });
      return;
    }
    case "roles":
      await enableRoleLogin(databaseUrl(), appDatabaseUrl(), APP_ROLE);
      await enableRoleLogin(databaseUrl(), aiToolsDatabaseUrl(), AI_TOOLS_ROLE);
      log({ event: "db.roles", status: "ok", roles: [APP_ROLE, AI_TOOLS_ROLE], login: true });
      return;
    case "create-analyst": {
      const [email, name] = args;
      if (!email || !name) throw new Error('usage: npm run analyst:create -- <email> "<name>" (password in ANALYST_PASSWORD)');
      const password = requireEnv("ANALYST_PASSWORD");
      const created = await withOwnerDb((db) => createAnalyst(db, { email, name, password }));
      log({ event: "analyst.create", status: "ok", analystId: created.id, email: created.email });
      return;
    }
    default:
      throw new Error(`unknown command "${command ?? ""}" (expected migrate, seed, roles or create-analyst)`);
  }
}

main(process.argv.slice(2)).catch((error: unknown) => {
  log({ event: "db.cli", status: "error", message: error instanceof Error ? error.message : String(error) });
  process.exitCode = 1;
});
