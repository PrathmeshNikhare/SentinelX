import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SeverityBadge, StatusBadge } from "@/components/console/badges";
import { EventTable } from "@/components/console/event-table";
import { DataUnavailable, EmptyState, Mono } from "@/components/console/states";
import { formatUtc } from "@/lib/format";
import { requireSession } from "@/server/auth/session";
import { load } from "@/server/load";
import { getIncident } from "@/server/queries/incidents";

export const metadata: Metadata = { title: "Incident" };

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  if (!(await requireSession())) return <DataUnavailable what="Incident details" />;
  const { id } = await params;
  const incident = await load("incident", () => getIncident(id));
  if (!incident.ok) return <DataUnavailable what="Incident details" />;
  if (!incident.data) notFound();
  const data = incident.data;

  return (
    <article className="flex flex-col gap-6">
      <header>
        <Link href="/incidents" className="text-muted-foreground hover:underline">
          ← Incidents
        </Link>
        <h1 className="mt-1 text-lg font-semibold tracking-tight">{data.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Mono>{data.id}</Mono>
          <SeverityBadge severity={data.severity} />
          <StatusBadge status={data.status} />
        </div>
      </header>

      <section aria-label="Risk and identity">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-5">
          <div>
            <dt className="text-muted-foreground">Risk score</dt>
            <dd className="font-mono text-xl" data-testid="risk-score">
              {data.riskScore}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Primary user</dt>
            <dd>
              <Mono>{data.primaryUserId ?? "—"}</Mono>
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Primary IP</dt>
            <dd>
              <Mono>{data.primaryIp ?? "—"}</Mono>
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Started (UTC)</dt>
            <dd>
              <Mono>{formatUtc(data.startedAt)}</Mono>
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Updated (UTC)</dt>
            <dd>
              <Mono>{formatUtc(data.updatedAt)}</Mono>
            </dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="related-events">
        <h2 id="related-events" className="mb-2 font-semibold">
          Related events
        </h2>
        {data.events.length === 0 ? (
          <EmptyState title="No linked events" />
        ) : (
          <EventTable events={data.events} />
        )}
      </section>

      <p className="text-muted-foreground">
        Detection signals, evidence, MITRE ATT&amp;CK mapping, the investigation trace and the verdict appear here once the
        detection and investigation pipeline produces them.
      </p>
    </article>
  );
}
