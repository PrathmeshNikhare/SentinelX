import "server-only";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { bearerToken, checkIngestToken } from "../ingest/token.ts";
import { SESSION_COOKIE } from "./auth/session.ts";
import { findActiveSession, type SessionAnalyst } from "./auth/session-store.ts";
import { db } from "./db.ts";
import { logError } from "./log.ts";

export const apiError = (status: number, code: string, message: string, extra: Record<string, unknown> = {}) =>
  NextResponse.json({ error: { code, message, ...extra } }, { status });

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

/**
 * Ingestion auth (D-041): a Bearer INGEST_API_TOKEN (no database access) or, without an Authorization header,
 * a valid analyst session.
 */
export async function withIngestAuth(
  route: string,
  request: Request,
  handler: (auth: "token" | "session") => Promise<Response>,
): Promise<Response> {
  if (!request.headers.has("authorization")) return withSession(route, () => handler("session"));
  const token = bearerToken(request.headers.get("authorization"));
  const check = token ? checkIngestToken(token, process.env.INGEST_API_TOKEN) : "invalid";
  if (check === "misconfigured") {
    logError("ingest.token_misconfigured", new Error("INGEST_API_TOKEN is shorter than 32 characters"), { route });
  }
  if (check !== "valid") return apiError(401, "unauthorized", "Invalid or disabled ingest token.");
  try {
    return await handler("token");
  } catch (error) {
    logError("api.handler_failed", error, { route });
    return apiError(503, "unavailable", "The request could not be completed.");
  }
}
