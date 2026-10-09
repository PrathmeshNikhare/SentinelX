import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SeverityBadge, StatusBadge } from "@/components/console/badges";
import { DataUnavailable, EmptyState, Mono } from "@/components/console/states";
import { AutoRefresh } from "@/components/incident/auto-refresh";
import {
  DetectionSignals,
  EvidenceList,
  MitreList,
  Recommendations,
  ReviewBanner,
  Section,
  SummaryFacts,
  Timeline,
  TraceList,
  VerdictPanel,
} from "@/components/incident/sections";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatUtc } from "@/lib/format";
import { INCIDENT_TRANSITIONS, TRANSITION_LABELS } from "@/lib/incident-lifecycle";
import { parseFindings, parseVerdict, summarize } from "@/lib/investigation-view";
import { requireSession } from "@/server/auth/session";
import { load } from "@/server/load";
import { getIncident } from "@/server/queries/incidents";
import { type InvestigationDetail, getTechniques, latestInvestigationDetail } from "@/server/queries/investigations";
import { changeIncidentStatus, requestInvestigation } from "./actions";

export const metadata: Metadata = { title: "Incident" };

const INVESTIGATION_NOTICES: Record<string, string> = {
  queued: "Investigation queued. This page refreshes until it finishes.",
  in_progress: "An investigation of this incident is already running.",
  not_found: "The AI service does not know this incident.",
  unavailable: "The AI service is unavailable. Try again later.",
};

/** ATT&CK IDs the run touched: the verdict's, found lookups and MITRE knowledge hits (display only). */
function techniqueIds(run: InvestigationDetail | null, verdictIds: string[]): string[] {
  const retrieved = (run?.evidence ?? []).flatMap((e) => {
    const data = (e.data ?? {}) as { found?: unknown; source?: unknown; external_id?: unknown };
    if (e.sourceType === "mitre" && data.found === true) return [e.sourceId];
    if (e.sourceType === "knowledge" && data.source === "mitre-attack" && typeof data.external_id === "string") {
      return [data.external_id];
    }
    return [];
  });
  return [...new Set([...verdictIds, ...retrieved])];
}

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
  const runLoad = await load("latest investigation", () => latestInvestigationDetail(id));
  const run = runLoad.ok ? runLoad.data : null;
  const verdict = parseVerdict(run?.verdict);
  const findings = parseFindings(run?.validationErrors);
  const ids = techniqueIds(run, verdict?.mitre_techniques ?? []);
  const techniques = await load("MITRE techniques", () => getTechniques(ids));
  const summary = summarize(data.events, data.alerts);
  const notice = INVESTIGATION_NOTICES[(await searchParams).investigation ?? ""];
  const active = run?.status === "queued" || run?.status === "running";
  const cited = new Set(verdict?.evidence_ids ?? []);
  const claims = new Map((run?.evidence ?? []).map((e) => [e.id, e.claim]));
  const noRun = <EmptyState title="No investigation yet.">Press Investigate to gather evidence with the AI service.</EmptyState>;

  return (
    <article className="flex flex-col gap-6">
      <AutoRefresh active={active} />
      <header>
        <Link href="/incidents" className="text-muted-foreground hover:underline">
          ← Incidents
        </Link>
        <h1 className="mt-1 text-lg font-semibold tracking-tight">{data.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Mono>{data.id}</Mono>
          <SeverityBadge severity={data.severity} />
          <StatusBadge status={data.status} />
          {summary.demo ? (
            <Badge variant="outline" className="rounded-sm border-slate-400 bg-slate-100 px-1.5 py-0 text-[11px] text-slate-800">
              demo scenario data
            </Badge>
          ) : null}
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
            <dt className="text-muted-foreground">Risk score (deterministic)</dt>
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

      <Section id="summary" title="Summary" note="Facts from detection; no AI interpretation.">
        <SummaryFacts summary={summary} />
      </Section>

      <Section id="timeline" title="Timeline" note="Linked events in order, with the rules they triggered.">
        <Timeline incident={data} />
      </Section>

      <Section id="detection-signals" title="Detection signals" note="Alerts and how the deterministic risk was computed.">
        <DetectionSignals incident={data} />
      </Section>

      <Section id="investigation" title="Investigation trace" note="Each step the agent took; fallback marks the deterministic plan.">
        <form action={requestInvestigation} className="mb-3 flex flex-wrap items-center gap-3" aria-label="Investigation">
          <input type="hidden" name="incidentId" value={data.id} />
          <Button type="submit" variant="outline" size="sm" disabled={active}>
            Investigate
          </Button>
          {notice ? (
            <span role="status" className="text-muted-foreground">
              {notice}
            </span>
          ) : null}
        </form>
        {!runLoad.ok ? (
          <DataUnavailable what="Investigation results" />
        ) : !run ? (
          noRun
        ) : (
          <>
            <dl className="mb-3 grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-5" data-testid="latest-investigation">
              <div>
                <dt className="text-muted-foreground">Latest run</dt>
                <dd>
                  <Mono>{run.id}</Mono>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Status</dt>
                <dd>{active ? `${run.status}…` : run.status}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Requires review</dt>
                <dd>{run.requiresReview ? "yes" : "no"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Model / prompt</dt>
                <dd>
                  <Mono>
                    {run.modelName ?? "—"} / {run.promptVersion ?? "—"}
                  </Mono>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Created (UTC)</dt>
                <dd>
                  <Mono>{formatUtc(run.createdAt)}</Mono>
                </dd>
              </div>
            </dl>
            {run.status === "failed" ? (
              <div role="alert" className="mb-3 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-red-900">
                <p className="font-medium">Investigation failed</p>
                <p className="mt-1">{run.errorMessage ?? "No reason recorded."} Evidence gathered so far is kept below.</p>
              </div>
            ) : null}
            <TraceList trace={run.trace} />
          </>
        )}
      </Section>

      <Section id="evidence" title="Evidence" note="Every row was stored by the investigation; the verdict may cite only these IDs.">
        {run ? <EvidenceList evidence={run.evidence} cited={cited} /> : <EmptyState title="No evidence yet" />}
      </Section>

      <Section id="mitre" title="MITRE ATT&CK" note="Curated techniques referenced by the verdict or retrieved as evidence.">
        {!techniques.ok ? (
          <DataUnavailable what="MITRE techniques" />
        ) : (
          <MitreList techniques={techniques.data} cited={new Set(verdict?.mitre_techniques ?? [])} evidence={run?.evidence ?? []} />
        )}
      </Section>

      <Section id="verdict" title="Verdict" note="AI-generated from the evidence above; validated against it before it is shown.">
        {run && run.requiresReview && !active ? <ReviewBanner findings={findings} accepted={verdict !== null} /> : null}
        {verdict ? (
          <div className="mt-3">
            <VerdictPanel verdict={verdict} deterministicSeverity={data.severity} riskScore={data.riskScore} claims={claims} />
          </div>
        ) : run && !active ? (
          <EmptyState title="No accepted verdict">
            {run.status === "failed" ? "The run failed before a verdict was produced." : "See the review findings above."}
          </EmptyState>
        ) : (
          <EmptyState title={run ? "Verdict pending" : "No verdict yet"} />
        )}
      </Section>

      <Section id="recommendations" title="Recommendations" note="Suggestions for an analyst to approve. SentinelX takes no action itself.">
        {verdict ? <Recommendations items={verdict.recommendations} /> : <EmptyState title="No recommendations" />}
      </Section>
    </article>
  );
}
