import Link from "next/link";
import { SeverityBadge } from "@/components/console/badges";
import { IncidentTable } from "@/components/console/incident-table";
import { DataUnavailable, EmptyState, Mono, PageHeader } from "@/components/console/states";
import { formatUtc } from "@/lib/format";
import { requireSession } from "@/server/auth/session";
import { load } from "@/server/load";
import { listIncidents } from "@/server/queries/incidents";
import { getOverview } from "@/server/queries/overview";

export default async function OverviewPage() {
  if (!(await requireSession())) return <DataUnavailable what="Overview data" />;
  const [overview, recent] = await Promise.all([load("overview", () => getOverview()), load("incidents", () => listIncidents(5))]);

  return (
    <>
      <PageHeader title="Overview" description="Current incident load and recent activity from persisted data." />
      {overview.ok ? (
        <section aria-label="Summary" className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded-md border p-3">
            <p className="text-muted-foreground">Open incidents</p>
            <p className="font-mono text-2xl" data-testid="open-incidents">
              {overview.data.openIncidents}
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {Object.entries(overview.data.openBySeverity).map(([severity, total]) => (
                <li key={severity} className="flex items-center gap-1">
                  <SeverityBadge severity={severity} />
                  <span className="font-mono">{total}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-md border p-3">
            <p className="text-muted-foreground">Security events, last 24 h</p>
            <p className="font-mono text-2xl" data-testid="events-24h">
              {overview.data.events24h}
            </p>
          </div>
          <div className="rounded-md border p-3">
            <p className="text-muted-foreground">Alerts, last 24 h</p>
            <p className="font-mono text-2xl" data-testid="alerts-24h">
              {overview.data.alerts24h}
            </p>
            <p className="mt-2 text-muted-foreground">
              As of <Mono>{formatUtc(overview.data.asOf)}</Mono>
            </p>
          </div>
        </section>
      ) : (
        <div className="mb-6">
          <DataUnavailable what="Summary counts" />
        </div>
      )}

      <section aria-labelledby="recent-incidents">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 id="recent-incidents" className="font-semibold">
            Recent incidents
          </h2>
          <Link href="/incidents" className="text-muted-foreground hover:underline">
            All incidents
          </Link>
        </div>
        {!recent.ok ? (
          <DataUnavailable what="Incidents" />
        ) : recent.data.length === 0 ? (
          <EmptyState title="No incidents">Incidents appear here when the detection pipeline correlates alerts.</EmptyState>
        ) : (
          <IncidentTable incidents={recent.data} />
        )}
      </section>
    </>
  );
}
