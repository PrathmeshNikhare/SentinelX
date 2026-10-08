// Session and credential storage (D-034). Takes the database as a parameter so it runs under any role.
import { createHash, randomBytes } from "node:crypto";
import { and, eq, gt, isNull } from "drizzle-orm";
import type { NodePgDatabase } from "drizzle-orm/node-postgres";
import { analysts, analystSessions } from "../../db/schema.ts";
import { dummyPasswordHash, verifyPassword } from "./password.ts";

export const SESSION_TTL_MS = 8 * 60 * 60 * 1000;
const TOKEN_FORMAT = /^[A-Za-z0-9_-]{43}$/; // 32 random bytes, base64url

export interface SessionAnalyst {
  sessionId: string;
  analystId: string;
  email: string;
  name: string;
}

export const normalizeEmail = (email: string): string => email.trim().toLowerCase();
export const hashSessionToken = (token: string): string => createHash("sha256").update(token).digest("hex");
export const isSessionTokenFormat = (token: string): boolean => TOKEN_FORMAT.test(token);

/** Returns the analyst when the credentials match, otherwise null. Unknown emails still pay the hash cost. */
export async function authenticate(
  db: NodePgDatabase,
  email: string,
  password: string,
): Promise<{ id: string; name: string } | null> {
  const [analyst] = await db
    .select({ id: analysts.id, name: analysts.name, passwordHash: analysts.passwordHash })
    .from(analysts)
    .where(eq(analysts.email, normalizeEmail(email)))
    .limit(1);
  if (!analyst) {
    await verifyPassword(password, await dummyPasswordHash());
    return null;
  }
  return (await verifyPassword(password, analyst.passwordHash)) ? { id: analyst.id, name: analyst.name } : null;
}

export async function createSession(
  db: NodePgDatabase,
  analystId: string,
  now: Date = new Date(),
): Promise<{ token: string; expiresAt: Date }> {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(now.getTime() + SESSION_TTL_MS);
  await db.insert(analystSessions).values({ analystId, tokenHash: hashSessionToken(token), expiresAt });
  return { token, expiresAt };
}

/** The session's analyst if the token is known, unrevoked and unexpired. */
export async function findActiveSession(
  db: NodePgDatabase,
  token: string,
  now: Date = new Date(),
): Promise<SessionAnalyst | null> {
  if (!isSessionTokenFormat(token)) return null;
  const [row] = await db
    .select({
      sessionId: analystSessions.id,
      analystId: analysts.id,
      email: analysts.email,
      name: analysts.name,
    })
    .from(analystSessions)
    .innerJoin(analysts, eq(analysts.id, analystSessions.analystId))
    .where(
      and(
        eq(analystSessions.tokenHash, hashSessionToken(token)),
        isNull(analystSessions.revokedAt),
        gt(analystSessions.expiresAt, now),
      ),
    )
    .limit(1);
  return row ?? null;
}

export async function revokeSession(db: NodePgDatabase, token: string, now: Date = new Date()): Promise<void> {
  if (!isSessionTokenFormat(token)) return;
  await db
    .update(analystSessions)
    .set({ revokedAt: now })
    .where(and(eq(analystSessions.tokenHash, hashSessionToken(token)), isNull(analystSessions.revokedAt)));
}
