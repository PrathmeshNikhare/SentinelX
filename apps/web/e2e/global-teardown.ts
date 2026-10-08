import pg from "pg";
import { E2E_DATABASE, ownerAdminUrl } from "./support.ts";

export default async function globalTeardown(): Promise<void> {
  const client = new pg.Client({ connectionString: ownerAdminUrl() });
  await client.connect();
  try {
    await client.query(`DROP DATABASE IF EXISTS ${E2E_DATABASE} WITH (FORCE)`);
  } finally {
    await client.end();
  }
}
