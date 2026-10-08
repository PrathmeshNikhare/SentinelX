"use server";

import { redirect } from "next/navigation";
import { clearSessionCookie } from "@/server/auth/session";
import { revokeSession } from "@/server/auth/session-store";
import { db } from "@/server/db";
import { logError, logEvent } from "@/server/log";

/** Revokes the session server-side (revoked_at) and clears the cookie. */
export async function logout(): Promise<void> {
  const token = await clearSessionCookie();
  if (token) {
    try {
      await revokeSession(db(), token);
      logEvent("auth.logout");
    } catch (error) {
      logError("auth.logout_revoke_failed", error);
    }
  }
  redirect("/login");
}
