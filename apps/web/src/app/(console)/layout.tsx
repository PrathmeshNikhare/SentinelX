import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { Sidebar } from "@/components/console/sidebar";
import { ServiceUnavailable } from "@/components/console/states";
import { Button } from "@/components/ui/button";
import { sessionState } from "@/server/auth/session";
import { logout } from "./actions";

export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const state = await sessionState();
  if (state.status === "unavailable") return <ServiceUnavailable />;
  if (state.status === "anonymous") redirect("/login");
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center justify-end gap-3 border-b px-4">
          <span className="text-muted-foreground" data-testid="analyst-name">
            {state.session.name}
          </span>
          <form action={logout}>
            <Button type="submit" variant="outline" size="sm">
              Sign out
            </Button>
          </form>
        </header>
        <main className="flex-1 p-4">{children}</main>
      </div>
    </div>
  );
}
