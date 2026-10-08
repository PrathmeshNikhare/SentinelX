"use server";

import { redirect } from "next/navigation";
import { MAX_PASSWORD_LENGTH } from "@/server/auth/password";
import { setSessionCookie } from "@/server/auth/session";
import { authenticate, createSession } from "@/server/auth/session-store";
import { db } from "@/server/db";
import { logError, logEvent } from "@/server/log";

// React 19 resets the form after the action; the email is echoed back (never the password) so it survives a retry.
export interface LoginState {
  error: string | null;
  email: string;
}

// Server Action: Next.js rejects cross-origin posts (D-034). Input is validated before any database access.
export async function login(_previous: LoginState, formData: FormData): Promise<LoginState> {
  const email = formData.get("email");
  const password = formData.get("password");
  const echoedEmail = typeof email === "string" ? email.slice(0, 320) : "";
  if (typeof email !== "string" || typeof password !== "string" || email.trim() === "" || password === "") {
    return { error: "Enter your email and password.", email: echoedEmail };
  }
  if (email.length > 320 || password.length > MAX_PASSWORD_LENGTH) {
    return { error: "Invalid email or password.", email: echoedEmail };
  }
  try {
    const analyst = await authenticate(db(), email, password);
    if (!analyst) {
      logEvent("auth.login_rejected", { reason: "invalid_credentials" });
      return { error: "Invalid email or password.", email: echoedEmail };
    }
    const { token, expiresAt } = await createSession(db(), analyst.id);
    await setSessionCookie(token, expiresAt);
    logEvent("auth.login", { analystId: analyst.id });
  } catch (error) {
    logError("auth.login_unavailable", error);
    return { error: "Sign-in is temporarily unavailable. Try again shortly.", email: echoedEmail };
  }
  redirect("/");
}
