import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed px-4 py-8 text-center" data-state="empty">
      <p className="font-medium">{title}</p>
      {children ? <p className="mt-1 text-muted-foreground">{children}</p> : null}
    </div>
  );
}

/** Degraded state: the view rendered, but its data source is unreachable. */
export function DataUnavailable({ what }: { what: string }) {
  return (
    <div role="alert" className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900" data-state="degraded">
      <p className="font-medium">{what} are unavailable</p>
      <p className="mt-1">The database could not be reached. Other parts of the console may still work; retry shortly.</p>
    </div>
  );
}

export function ServiceUnavailable() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div role="alert" className="max-w-md rounded-md border border-amber-300 bg-amber-50 p-5 text-amber-900" data-state="degraded">
        <h1 className="text-base font-semibold">Service unavailable</h1>
        <p className="mt-2">
          SentinelX cannot reach its database, so your session cannot be verified. Check that the PostgreSQL container is
          running, then reload this page.
        </p>
      </div>
    </main>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      {description ? <p className="text-muted-foreground">{description}</p> : null}
    </div>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-xs">{children}</span>;
}
