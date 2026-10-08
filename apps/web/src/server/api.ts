import "server-only";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "./auth/session.ts";
import { findActiveSession, type SessionAnalyst } from "./auth/session-store.ts";
import { db } from "./db.ts";
import { logError } from "./log.ts";

export const apiError = (status: number, code: string, message: string, extra: Record<string, string> = {}) =>
  NextResponse.json({ error: { code, message, ...extra } }, { status });

/** Placeholder for endpoints owned by a later phase (D-036). */
export const notImplemented = (phase: string) =>
  apiError(501, "not_implemented", `This endpoint is implemented in Phase ${phase}.`, { phase });

/** Authenticates the request from the session cookie: 401 without a valid session, 503 if the database is down. */
export async function withSession(
  route: string,
  handler: (session: SessionAnalyst) => Promise<Response>,
): Promise<Response> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return apiError(401, "unauthorized", "Sign in required.");
  let session: SessionAnalyst | null;
  try {
    session = await findActiveSession(db(), token);
  } catch (error) {
    logError("api.session_unavailable", error, { route });
    return apiError(503, "unavailable", "The database is unavailable.");
  }
  if (!session) return apiError(401, "unauthorized", "Sign in required.");
  try {
    return await handler(session);
  } catch (error) {
    logError("api.handler_failed", error, { route });
    return apiError(503, "unavailable", "The request could not be completed.");
  }
}
