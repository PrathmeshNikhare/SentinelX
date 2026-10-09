import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SeverityBadge, StatusBadge } from "@/components/console/badges";
import { EventTable } from "@/components/console/event-table";
import { DataUnavailable, EmptyState, Mono } from "@/components/console/states";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/lib/format";
import { INCIDENT_TRANSITIONS, TRANSITION_LABELS } from "@/lib/incident-lifecycle";
import { requireSession } from "@/server/auth/session";
import { load } from "@/server/load";
import { getIncident } from "@/server/queries/incidents";
import { latestInvestigation } from "@/server/queries/investigations";
import { changeIncidentStatus, requestInvestigation } from "./actions";

export const metadata: Metadata = { title: "Incident" };

const INVESTIGATION_NOTICES: Record<string, string> = {
  queued: "Investigation queued. Reload to follow its status.",
  in_progress: "An investigation of this incident is already running.",
  not_found: "The AI service does not know this incident.",
  unavailable: "The AI service is unavailable. Try again later.",
};

export default async function IncidentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ investigation?: string }>;
}) {
  if (!(await requireSession())) return <DataUnavailable what="Incident details" />;
  const { id } = await params;
  const incident = await load("incident", () => getIncident(id));
  if (!incident.ok) return <DataUnavailable what="Incident details" />;
  if (!incident.data) notFound();
  const data = incident.data;
  const run = await load("latest investigation", () => latestInvestigation(id));
  const notice = INVESTIGATION_NOTICES[(await searchParams).investigation ?? ""];

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
        <form action={changeIncidentStatus} className="mt-3 flex gap-2" aria-label="Incident status">
          <input type="hidden" name="incidentId" value={data.id} />
          {INCIDENT_TRANSITIONS[data.status].map((next) => (
            <Button key={next} type="submit" name="status" value={next} variant="outline" size="sm">
              {TRANSITION_LABELS[next]}
            </Button>
          ))}
        </form>
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

      <section aria-labelledby="investigation">
        <h2 id="investigation" className="mb-2 font-semibold">
          Investigation
        </h2>
        <form action={requestInvestigation} className="flex items-center gap-3" aria-label="Investigation">
          <input type="hidden" name="incidentId" value={data.id} />
          <Button type="submit" variant="outline" size="sm">
            Investigate
          </Button>
          {notice ? (
            <span role="status" className="text-muted-foreground">
              {notice}
            </span>
          ) : null}
        </form>
        {!run.ok ? (
          <p className="mt-2 text-muted-foreground">Investigation history is unavailable.</p>
        ) : run.data ? (
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-4" data-testid="latest-investigation">
            <div>
              <dt className="text-muted-foreground">Latest run</dt>
              <dd>
                <Mono>{run.data.id}</Mono>
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd>{run.data.status}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Requires review</dt>
              <dd>{run.data.requiresReview ? "yes" : "no"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Created (UTC)</dt>
              <dd>
                <Mono>{formatUtc(run.data.createdAt)}</Mono>
              </dd>
            </div>
          </dl>
        ) : (
          <p className="mt-2 text-muted-foreground">No investigation yet.</p>
        )}
      </section>

      <p className="text-muted-foreground">
        The verdict, evidence, MITRE ATT&amp;CK mapping and the investigation trace are served by{" "}
        <Mono>GET /api/investigations/:id</Mono> and rendered here in Phase 11.
      </p>
    </article>
  );
}
