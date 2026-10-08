// Incident lifecycle (D-054). Detection never changes status; analysts do, through these transitions only.
import { incidentStatus } from "../db/schema.ts";

export type IncidentStatus = (typeof incidentStatus.enumValues)[number];

export const INCIDENT_TRANSITIONS: Record<IncidentStatus, readonly IncidentStatus[]> = {
  open: ["investigating", "resolved"],
  investigating: ["open", "resolved"],
  resolved: ["open"],
};

export const TRANSITION_LABELS: Record<IncidentStatus, string> = {
  investigating: "Start investigating",
  resolved: "Resolve",
  open: "Reopen",
};

export const isIncidentStatus = (value: unknown): value is IncidentStatus =>
  typeof value === "string" && (incidentStatus.enumValues as readonly string[]).includes(value);

export const canTransition = (from: IncidentStatus, to: IncidentStatus): boolean => INCIDENT_TRANSITIONS[from].includes(to);

/** States from which `to` may be entered; used as the guard of the conditional UPDATE. */
export const sourcesFor = (to: IncidentStatus): IncidentStatus[] =>
  incidentStatus.enumValues.filter((from) => canTransition(from, to));
