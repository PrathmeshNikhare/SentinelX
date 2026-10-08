import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { sessionState } from "@/server/auth/session";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage() {
  // With the database down the form still renders; the action reports the outage.
  if ((await sessionState()).status === "ok") redirect("/");
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-6">
      <div className="w-full max-w-sm rounded-md border bg-background p-6">
        <h1 className="text-base font-semibold">SentinelX</h1>
        <p className="mb-5 text-muted-foreground">Sign in to the security operations console.</p>
        <LoginForm />
      </div>
    </main>
  );
}
