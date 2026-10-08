// Owner-only administration: enabling role logins (D-035, D-061) and creating analyst accounts (D-034).
import type { NodePgDatabase } from "drizzle-orm/node-postgres";
import pg from "pg";
import { hashPassword, passwordPolicyError } from "../server/auth/password.ts";
import { normalizeEmail } from "../server/auth/session-store.ts";
import { analysts } from "./schema.ts";

export const APP_ROLE = "sentinelx_app";
export const AI_TOOLS_ROLE = "sentinelx_ai_tools";
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Enables LOGIN for `role` with the password embedded in `roleUrl` (APP_DATABASE_URL, AI_TOOLS_DATABASE_URL). */
export async function enableRoleLogin(ownerUrl: string, roleUrl: string, role: string): Promise<void> {
  const parsed = new URL(roleUrl);
  const user = decodeURIComponent(parsed.username);
  const password = decodeURIComponent(parsed.password);
  if (user !== role) throw new Error(`the ${role} connection string must connect as ${role}, not "${user}"`);
  if (password.length < 8) throw new Error(`the ${role} connection string must include a password of at least 8 characters`);
  const client = new pg.Client({ connectionString: ownerUrl });
  await client.connect();
  try {
    await client.query(`ALTER ROLE ${client.escapeIdentifier(role)} WITH LOGIN PASSWORD ${client.escapeLiteral(password)}`);
  } finally {
    await client.end();
  }
}

export const enableAppRoleLogin = (ownerUrl: string, appUrl: string): Promise<void> =>
  enableRoleLogin(ownerUrl, appUrl, APP_ROLE);

export async function createAnalyst(
  db: NodePgDatabase,
  input: { email: string; name: string; password: string },
): Promise<{ id: string; email: string }> {
  const email = normalizeEmail(input.email);
  const name = input.name.trim();
  if (!EMAIL.test(email) || email.length > 320) throw new Error(`invalid email "${input.email}"`);
  if (name === "" || name.length > 200) throw new Error("name must be 1-200 characters");
  const policyError = passwordPolicyError(input.password);
  if (policyError) throw new Error(policyError);
  const passwordHash = await hashPassword(input.password);
  const [created] = await db
    .insert(analysts)
    .values({ email, name, passwordHash })
    .onConflictDoNothing({ target: analysts.email })
    .returning({ id: analysts.id, email: analysts.email });
  if (!created) throw new Error(`analyst ${email} already exists`);
  return created;
}
