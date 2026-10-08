import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";
import { db } from "../db.ts";
import { load } from "../load.ts";
import { findActiveSession, type SessionAnalyst } from "./session-store.ts";

export const SESSION_COOKIE = "sx_session";

export type SessionState =
  | { status: "ok"; session: SessionAnalyst }
  | { status: "anonymous" }
  | { status: "unavailable" }; // PostgreSQL unreachable: the session cannot be verified

/** Session state for this request, resolved once per request. Never throws for database outages. */
export const sessionState = cache(async (): Promise<SessionState> => {
  const loaded = await load("session", async () => {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    return token ? findActiveSession(db(), token) : null;
  });
  if (!loaded.ok) return { status: "unavailable" };
  return loaded.data ? { status: "ok", session: loaded.data } : { status: "anonymous" };
});

/**
 * For pages: every page checks the session itself because layouts are not re-run on client navigation.
 * Redirects anonymous visitors; returns null when the database is unavailable so the page can degrade.
 */
export async function requireSession(): Promise<SessionAnalyst | null> {
  const state = await sessionState();
  if (state.status === "anonymous") redirect("/login");
  return state.status === "ok" ? state.session : null;
}

export async function setSessionCookie(token: string, expiresAt: Date): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires: expiresAt,
  });
}

export async function clearSessionCookie(): Promise<string | undefined> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  jar.delete(SESSION_COOKIE);
  return token;
}
