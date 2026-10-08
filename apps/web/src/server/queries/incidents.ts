import "server-only";
import { asc, desc, eq, sql } from "drizzle-orm";
import { incidentEvents, incidents, securityEvents } from "../../db/schema.ts";
import { isIncidentId } from "../../lib/ids.ts";
import { canTransition, type IncidentStatus } from "../../lib/incident-lifecycle.ts";
import { db } from "../db.ts";

const MAX_INCIDENTS = 100;
const MAX_INCIDENT_EVENTS = 200;

const incidentColumns = {
  id: incidents.id,
  title: incidents.title,
  status: incidents.status,
  severity: incidents.severity,
  riskScore: incidents.riskScore,
  primaryUserId: incidents.primaryUserId,
  primaryIp: incidents.primaryIp,
  startedAt: incidents.startedAt,
  updatedAt: incidents.updatedAt,
};

export async function listIncidents(limit = MAX_INCIDENTS) {
  return db()
    .select(incidentColumns)
    .from(incidents)
    .orderBy(desc(incidents.updatedAt))
    .limit(Math.min(limit, MAX_INCIDENTS));
}

export type IncidentSummary = Awaited<ReturnType<typeof listIncidents>>[number];

/** Incident with its linked events, or null if the id is malformed or unknown. */
export async function getIncident(id: string) {
  if (!isIncidentId(id)) return null;
  const [incident] = await db().select(incidentColumns).from(incidents).where(eq(incidents.id, id)).limit(1);
  if (!incident) return null;
  const events = await db()
    .select({
      id: securityEvents.id,
      externalEventId: securityEvents.externalEventId,
      occurredAt: securityEvents.occurredAt,
      userId: securityEvents.userId,
      sourceIp: securityEvents.sourceIp,
      eventType: securityEvents.eventType,
      action: securityEvents.action,
      resource: securityEvents.resource,
      status: securityEvents.status,
    })
    .from(incidentEvents)
    .innerJoin(securityEvents, eq(securityEvents.id, incidentEvents.eventId))
    .where(eq(incidentEvents.incidentId, id))
    .orderBy(asc(securityEvents.occurredAt))
    .limit(MAX_INCIDENT_EVENTS);
  return { ...incident, events };
}

export type TransitionResult =
  | { ok: true; from: IncidentStatus; to: IncidentStatus }
  | { ok: false; reason: "not_found" }
  | { ok: false; reason: "invalid_transition"; current: IncidentStatus };

/** Atomic lifecycle change (D-054): the row is locked, the transition checked, then updated in one transaction. */
export async function transitionIncident(id: string, to: IncidentStatus): Promise<TransitionResult> {
  if (!isIncidentId(id)) return { ok: false, reason: "not_found" };
  return db().transaction(async (tx) => {
    const [row] = await tx
      .select({ status: incidents.status })
      .from(incidents)
      .where(eq(incidents.id, id))
      .for("update");
    if (!row) return { ok: false, reason: "not_found" } as const;
    if (!canTransition(row.status, to)) return { ok: false, reason: "invalid_transition", current: row.status } as const;
    await tx.update(incidents).set({ status: to, updatedAt: sql`now()` }).where(eq(incidents.id, id));
    return { ok: true, from: row.status, to } as const;
  });
}
