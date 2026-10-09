// Incident page sections (Phase 11, docs/09 order). Server components: they render data, they fetch nothing.
import type { ReactNode } from "react";
import { SeverityBadge } from "@/components/console/badges";
import { EmptyState, Mono } from "@/components/console/states";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatUtc } from "@/lib/format";
import {
  ACTION_LABELS,
  EFFECT_LABELS,
  FINDING_LABELS,
  type Finding,
  formatDuration,
  type IncidentSummary,
  previewJson,
  SOURCE_TYPE_LABELS,
  techniqueEvidence,
  type VerdictView,
} from "@/lib/investigation-view";
import { cn } from "@/lib/utils";
import type { IncidentDetail } from "@/server/queries/incidents";
import type { InvestigationDetail } from "@/server/queries/investigations";

type Evidence = InvestigationDetail["evidence"][number];
type TraceStep = InvestigationDetail["trace"][number];
type Technique = { techniqueId: string; name: string; tactics: string[]; description: string };

const chip = "rounded-sm px-1.5 py-0 font-mono text-[11px]";

export function Section({ id, title, note, children }: { id: string; title: string; note?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="scroll-mt-4">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3">
        <h2 id={id} className="font-semibold">
          {title}
        </h2>
        {note ? <p className="text-muted-foreground">{note}</p> : null}
      </div>
      {children}
    </section>
  );
}

/** Links an evidence ID to its row in the evidence section. */
export function EvidenceRef({ id }: { id: string }) {
  return (
    <a href={`#${id}`} className="font-mono text-xs text-sky-800 underline-offset-2 hover:underline">
      {id}
    </a>
  );
}

export function SummaryFacts({ summary }: { summary: IncidentSummary }) {
  const facts: [string, ReactNode][] = [
    ["Events", summary.events],
    ["Time span (UTC)", summary.first && summary.last ? `${formatUtc(summary.first)} → ${formatUtc(summary.last)}` : "—"],
    ["Duration", formatDuration(summary.durationSeconds)],
    ["Users", summary.users.join(", ") || "—"],
    ["Source IPs", summary.sourceIps.join(", ") || "—"],
    ["Alerts", summary.alerts],
    ["Highest alert risk", summary.maxAlertRisk ?? "—"],
    ["Detection rules", summary.rules.join(", ") || "none"],
  ];
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="incident-summary">
      {facts.map(([label, value]) => (
        <div key={label}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="font-mono text-xs break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Timeline({ incident }: { incident: IncidentDetail }) {
  if (incident.events.length === 0) return <EmptyState title="No linked events" />;
  const riskByEvent = new Map(incident.alerts.map((a) => [a.eventId, a]));
  return (
    <Table data-testid="timeline">
      <TableHeader>
        <TableRow>
          <TableHead>Time (UTC)</TableHead>
          <TableHead>Event ID</TableHead>
          <TableHead>User</TableHead>
          <TableHead>Source IP</TableHead>
          <TableHead>Activity</TableHead>
          <TableHead>Resource</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Detection</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {incident.events.map((event) => {
          const alert = riskByEvent.get(event.id);
          return (
            <TableRow key={event.id}>
              <TableCell>
                <Mono>{formatUtc(event.occurredAt)}</Mono>
              </TableCell>
              <TableCell>
                <Mono>{event.externalEventId}</Mono>
              </TableCell>
              <TableCell>
                <Mono>{event.userId}</Mono>
              </TableCell>
              <TableCell>
                <Mono>{event.sourceIp}</Mono>
              </TableCell>
              <TableCell>
                {event.eventType} / {event.action}
              </TableCell>
              <TableCell className="max-w-64 truncate" title={event.resource}>
                {event.resource}
              </TableCell>
              <TableCell className={cn(event.status === "failed" && "text-red-800")}>{event.status}</TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {alert ? (
                    <Badge variant="outline" className={cn(chip, "border-red-300 bg-red-50 text-red-800")}>
                      alert · risk {alert.riskScore}
                    </Badge>
                  ) : null}
                  {event.signals.map((s) => (
                    <Badge key={s.ruleName} variant="outline" className={chip} title={s.reason}>
                      {s.ruleName}
                    </Badge>
                  ))}
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function DetectionSignals({ incident }: { incident: IncidentDetail }) {
  if (incident.alerts.length === 0) return <EmptyState title="No alerts linked to this incident" />;
  const events = new Map(incident.events.map((e) => [e.id, e]));
  return (
    <Table data-testid="detection-signals">
      <TableHeader>
        <TableRow>
          <TableHead>Event</TableHead>
          <TableHead>Risk</TableHead>
          <TableHead>Severity</TableHead>
          <TableHead>Anomaly</TableHead>
          <TableHead>Rule signals</TableHead>
          <TableHead>Risk components</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {incident.alerts.map((alert) => {
          const event = events.get(alert.eventId);
          const c = alert.reasons.components;
          return (
            <TableRow key={alert.id}>
              <TableCell>
                <Mono>{event ? `${formatUtc(event.occurredAt)} ${event.externalEventId}` : alert.eventId}</Mono>
              </TableCell>
              <TableCell className="font-mono">{alert.riskScore}</TableCell>
              <TableCell>
                <SeverityBadge severity={alert.severity} />
              </TableCell>
              <TableCell className="font-mono">{alert.anomalyScore.toFixed(2)}</TableCell>
              <TableCell className="whitespace-normal">
                <ul className="space-y-0.5">
                  {(alert.reasons.signals ?? []).map((s) => (
                    <li key={s.rule}>
                      <Mono>
                        {s.rule} ({s.score})
                      </Mono>{" "}
                      <span className="text-muted-foreground">{s.reason}</span>
                    </li>
                  ))}
                </ul>
              </TableCell>
              <TableCell className="whitespace-normal">
                {c ? (
                  <>
                    <Mono>
                      R {c.rule} · A {c.anomaly} · P {c.reputation} · C {c.context}
                    </Mono>
                    {alert.reasons.formula ? <p className="font-mono text-[11px] text-muted-foreground">{alert.reasons.formula}</p> : null}
                  </>
                ) : (
                  "—"
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function EvidenceList({ evidence, cited }: { evidence: Evidence[]; cited: Set<string> }) {
  if (evidence.length === 0) return <EmptyState title="No evidence collected" />;
  return (
    <ol className="divide-y rounded-md border" data-testid="evidence">
      {evidence.map((item) => (
        <li key={item.id} id={item.id} className={cn("scroll-mt-4 px-3 py-2 target:bg-sky-50", cited.has(item.id) && "bg-slate-50")}>
          <div className="flex flex-wrap items-center gap-2">
            <Mono>{item.id}</Mono>
            <Badge variant="outline" className={chip}>
              {SOURCE_TYPE_LABELS[item.sourceType] ?? item.sourceType}
            </Badge>
            <Mono>{item.sourceId}</Mono>
            {cited.has(item.id) ? (
              <Badge variant="outline" className={cn(chip, "border-sky-300 bg-sky-50 text-sky-800")}>
                cited in verdict
              </Badge>
            ) : null}
          </div>
          <p className="mt-1 break-words">{item.claim}</p>
          <details className="mt-1">
            <summary className="cursor-pointer text-muted-foreground">Source data</summary>
            <pre className="mt-1 max-h-64 overflow-auto rounded bg-slate-50 p-2 font-mono text-[11px]">{previewJson(item.data)}</pre>
          </details>
        </li>
      ))}
    </ol>
  );
}

export function MitreList({
  techniques,
  cited,
  evidence,
}: {
  techniques: Technique[];
  cited: Set<string>;
  evidence: Evidence[];
}) {
  if (techniques.length === 0) return <EmptyState title="No MITRE ATT&CK techniques referenced" />;
  return (
    <ul className="divide-y rounded-md border" data-testid="mitre">
      {techniques.map((t) => {
        const sources = techniqueEvidence(t.techniqueId, evidence);
        return (
          <li key={t.techniqueId} className="px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <Mono>{t.techniqueId}</Mono>
              <span className="font-medium">{t.name}</span>
              <span className="text-muted-foreground">{t.tactics.join(", ")}</span>
              {cited.has(t.techniqueId) ? (
                <Badge variant="outline" className={cn(chip, "border-sky-300 bg-sky-50 text-sky-800")}>
                  in verdict
                </Badge>
              ) : null}
            </div>
            <p className="mt-1">{t.description}</p>
            <p className="mt-1 text-muted-foreground">
              Retrieved as evidence:{" "}
              {sources.length ? sources.map((id, i) => [i ? ", " : "", <EvidenceRef key={id} id={id} />]) : "not retrieved"}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function traceOutcome(step: TraceStep): string {
  const result = (step.result ?? {}) as Record<string, unknown>;
  if (step.actionType === "choose_action") return String(result.reason ?? "");
  if (step.actionType === "tool_call") return result.ok ? "ok" : `failed: ${String(result.error ?? "")}`;
  if (step.actionType === "load_incident") return `${String(result.events)} events, ${String(result.alerts)} alerts`;
  if (step.actionType === "build_verdict") {
    return result.failure ? String(result.failure) : `${String(result.attempts)} attempt(s), valid: ${String(result.valid)}`;
  }
  if (step.actionType === "validate_verdict") {
    return `accepted: ${String(result.accepted)}, requires review: ${String(result.requires_review ?? !result.accepted)}`;
  }
  return "";
}

export function TraceList({ trace }: { trace: TraceStep[] }) {
  if (trace.length === 0) return <EmptyState title="No trace steps yet" />;
  return (
    <Table data-testid="trace">
      <TableHeader>
        <TableRow>
          <TableHead>Step</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Origin</TableHead>
          <TableHead>Tool</TableHead>
          <TableHead>Input</TableHead>
          <TableHead>Outcome</TableHead>
          <TableHead>Evidence</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trace.map((step) => {
          const ids = Array.isArray(step.evidenceIds) ? (step.evidenceIds as string[]) : [];
          const input = step.actionType === "tool_call" && step.input ? JSON.stringify(step.input) : "";
          return (
            <TableRow key={step.stepIndex}>
              <TableCell className="font-mono">{step.stepIndex}</TableCell>
              <TableCell>{ACTION_LABELS[step.actionType] ?? step.actionType}</TableCell>
              <TableCell>
                {step.actionOrigin ? (
                  <Badge
                    variant="outline"
                    className={cn(chip, step.actionOrigin === "fallback" ? "border-amber-300 bg-amber-50 text-amber-800" : "")}
                  >
                    {step.actionOrigin}
                  </Badge>
                ) : (
                  "—"
                )}
              </TableCell>
              <TableCell>
                <Mono>{step.toolName ?? "—"}</Mono>
              </TableCell>
              <TableCell className="max-w-72 truncate" title={input}>
                <Mono>{input || "—"}</Mono>
              </TableCell>
              <TableCell className="max-w-80 whitespace-normal break-words">{traceOutcome(step)}</TableCell>
              <TableCell className="whitespace-normal">
                {ids.length > 4 ? `${ids.length} rows` : ids.map((id, i) => [i ? ", " : "", <EvidenceRef key={id} id={id} />])}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function ReviewBanner({ findings, accepted }: { findings: Finding[]; accepted: boolean }) {
  return (
    <div role="alert" className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900" data-testid="review-banner">
      <p className="font-medium">
        Requires analyst review{accepted ? "" : ": no verdict was accepted"}
      </p>
      {findings.length ? (
        <ul className="mt-1 list-disc pl-5">
          {findings.map((f, i) => (
            <li key={`${f.code}-${f.detail}-${i}`}>
              {FINDING_LABELS[f.code] ?? f.code} — <Mono>{f.detail}</Mono>{" "}
              <span className="text-amber-800">
                ({EFFECT_LABELS[f.effect] ?? f.effect}
                {f.attempt !== undefined ? `, attempt ${f.attempt + 1}` : ""})
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function VerdictPanel({
  verdict,
  deterministicSeverity,
  riskScore,
  claims,
}: {
  verdict: VerdictView;
  deterministicSeverity: string;
  riskScore: number;
  claims: Map<string, string>;
}) {
  return (
    <div className="rounded-md border px-4 py-3" data-testid="verdict">
      <p className="text-base font-semibold">{verdict.verdict}</p>
      <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">AI-assessed severity</dt>
          <dd>
            <SeverityBadge severity={verdict.severity} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Deterministic severity and risk</dt>
          <dd className="flex items-center gap-2">
            <SeverityBadge severity={deterministicSeverity} />
            <span className="font-mono text-xs">risk {riskScore}/100</span>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Confidence (model-reported, uncalibrated)</dt>
          <dd className="font-mono text-xs">{verdict.confidence.toFixed(2)}</dd>
        </div>
      </dl>
      <p className="mt-3 break-words">{verdict.summary}</p>
      <p className="mt-3 text-muted-foreground">Cited evidence</p>
      <ul className="mt-1 space-y-0.5">
        {verdict.evidence_ids.map((id) => (
          <li key={id}>
            <EvidenceRef id={id} /> <span className="text-muted-foreground">{claims.get(id) ?? ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Recommendations({ items }: { items: string[] }) {
  return (
    <ol className="list-decimal space-y-1 pl-5" data-testid="recommendations">
      {items.map((r, i) => (
        <li key={`${i}-${r}`}>{r}</li>
      ))}
    </ol>
  );
}
