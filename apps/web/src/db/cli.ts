// Usage: node src/db/cli.ts migrate|seed   (npm run db:migrate / npm run db:seed)
// Logs one JSON line per run; never logs the connection string.
import { drizzle } from "drizzle-orm/node-postgres";
import pg from "pg";
import { databaseUrl } from "./env.ts";
import { runMigrations } from "./migrate.ts";
import { seedReferenceData } from "./seed.ts";

const log = (fields: Record<string, unknown>) =>
  console.log(JSON.stringify({ ts: new Date().toISOString(), ...fields }));

async function main(command: string | undefined): Promise<void> {
  const url = databaseUrl();
  if (command === "migrate") {
    await runMigrations(url);
    log({ event: "db.migrate", status: "ok" });
  } else if (command === "seed") {
    const pool = new pg.Pool({ connectionString: url, max: 1 });
    try {
      const counts = await seedReferenceData(drizzle(pool));
      log({ event: "db.seed", status: "ok", ...counts });
    } finally {
      await pool.end();
    }
  } else {
    throw new Error(`unknown command "${command ?? ""}" (expected migrate or seed)`);
  }
}

main(process.argv[2]).catch((error: unknown) => {
  log({ event: "db.cli", status: "error", message: error instanceof Error ? error.message : String(error) });
  process.exitCode = 1;
});
