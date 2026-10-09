// Presentation helpers for the incident page (Phase 11). Pure: no data access, no business rules beyond labelling.

/** Human labels for verdict validation codes written by the AI service (D-073). Unknown codes show as-is. */
export const FINDING_LABELS: Record<string, string> = {
  schema: "Answer did not match the verdict schema",
  unknown_evidence_id: "Cited evidence that is not part of this investigation",
  unknown_mitre_technique: "MITRE technique outside the curated ATT&CK set",
  unsupported_mitre_technique: "MITRE technique not retrieved in this investigation",
  severity_disagreement: "AI-assessed severity differs from the deterministic severity",
  validation_unavailable: "The verdict could not be validated (database unavailable)",
};

export const EFFECT_LABELS: Record<string, string> = {
  reject: "rejected",
  review: "requires review",
  note: "note",
};

/** Trace action types (D-064). */
export const ACTION_LABELS: Record<string, string> = {
  load_incident: "Load incident",
  choose_action: "Choose next action",
  tool_call: "Run tool",
  build_verdict: "Build verdict",
  validate_verdict: "Validate verdict",
};

export const SOURCE_TYPE_LABELS: Record<string, string> = {
  event: "event",
  alert: "alert",
  user_history: "user history",
  ip_reputation: "IP reputation",
  related_logs: "related logs",
  mitre: "MITRE",
  knowledge: "knowledge",
};

export interface Finding {
  attempt?: number;
  code: string;
  detail: string;
  effect: string;
}

/** validation_errors_json is untyped jsonb; keep only well-formed findings. */
export function parseFindings(value: unknown): Finding[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (f): f is Finding =>
      typeof f === "object" && f !== null && typeof f.code === "string" && typeof f.detail === "string" && typeof f.effect === "string",
  );
}

export interface VerdictView {
  verdict: string;
  confidence: number;
  severity: string;
  summary: string;
  evidence_ids: string[];
  mitre_techniques: string[];
  recommendations: string[];
}

/** verdict_json holds only validated verdicts (D-019); still check the shape before rendering. */
export function parseVerdict(value: unknown): VerdictView | null {
  if (typeof value !== "object" || value === null) return null;
  const v = value as Record<string, unknown>;
  const strings = (x: unknown): x is string[] => Array.isArray(x) && x.every((s) => typeof s === "string");
  if (
    typeof v.verdict !== "string" ||
    typeof v.confidence !== "number" ||
    typeof v.severity !== "string" ||
    typeof v.summary !== "string" ||
    !strings(v.evidence_ids) ||
    !strings(v.mitre_techniques) ||
    !strings(v.recommendations)
  ) {
    return null;
  }
  return v as unknown as VerdictView;
}

interface TimelineEvent {
  externalEventId: string;
  occurredAt: Date;
  userId: string;
  sourceIp: string;
  signals: { ruleName: string }[];
}

export interface IncidentSummary {
  events: number;
  first: Date | null;
  last: Date | null;
  durationSeconds: number;
  users: string[];
  sourceIps: string[];
  rules: string[];
  alerts: number;
  maxAlertRisk: number | null;
  demo: boolean;
}

/** Deterministic facts for the summary section: counts and spans only, no interpretation. */
export function summarize(events: TimelineEvent[], alerts: { riskScore: number }[]): IncidentSummary {
  const times = events.map((e) => e.occurredAt.getTime());
  const first = times.length ? new Date(Math.min(...times)) : null;
  const last = times.length ? new Date(Math.max(...times)) : null;
  const unique = (values: string[]) => [...new Set(values)];
  return {
    events: events.length,
    first,
    last,
    durationSeconds: first && last ? Math.round((last.getTime() - first.getTime()) / 1000) : 0,
    users: unique(events.map((e) => e.userId)),
    sourceIps: unique(events.map((e) => e.sourceIp)),
    rules: unique(events.flatMap((e) => e.signals.map((s) => s.ruleName))),
    alerts: alerts.length,
    maxAlertRisk: alerts.length ? Math.max(...alerts.map((a) => a.riskScore)) : null,
    demo: events.some((e) => e.externalEventId.startsWith("demo-")),
  };
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${seconds % 60} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

/** Compact JSON for display, cut at `max` characters so one evidence row cannot flood the page. */
export function previewJson(value: unknown, max = 2000): string {
  const text = JSON.stringify(value, null, 2) ?? "null";
  return text.length <= max ? text : `${text.slice(0, max)}\n… (${text.length - max} more characters)`;
}

/** Evidence rows that mention a technique: MITRE lookups by ID, knowledge hits by external ID. Display linking only. */
export function techniqueEvidence(
  technique: string,
  evidence: { id: string; sourceType: string; sourceId: string; data: unknown }[],
): string[] {
  return evidence
    .filter((e) => {
      if (e.sourceType === "mitre") return e.sourceId === technique;
      if (e.sourceType !== "knowledge" || typeof e.data !== "object" || e.data === null) return false;
      return (e.data as { external_id?: unknown }).external_id === technique;
    })
    .map((e) => e.id);
}
