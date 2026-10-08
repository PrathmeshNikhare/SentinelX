import "server-only";
import { count, gte, ne } from "drizzle-orm";
import { alerts, incidents, securityEvents, severity } from "../../db/schema.ts";
import { db } from "../db.ts";

export type Severity = (typeof severity.enumValues)[number];

/** Real counts only (D-036): open incidents by severity, plus events and alerts in the last 24 hours. */
export async function getOverview(now: Date = new Date()) {
  const since = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const [bySeverity, [events], [alertCount]] = await Promise.all([
    db()
      .select({ severity: incidents.severity, total: count() })
      .from(incidents)
      .where(ne(incidents.status, "resolved"))
      .groupBy(incidents.severity),
    db().select({ total: count() }).from(securityEvents).where(gte(securityEvents.occurredAt, since)),
    db().select({ total: count() }).from(alerts).where(gte(alerts.createdAt, since)),
  ]);
  // Most severe first: that is the order an operator scans in.
  const openBySeverity = Object.fromEntries([...severity.enumValues].reverse().map((s) => [s, 0])) as Record<Severity, number>;
  for (const row of bySeverity) openBySeverity[row.severity] = row.total;
  return {
    openIncidents: Object.values(openBySeverity).reduce((a, b) => a + b, 0),
    openBySeverity,
    events24h: events?.total ?? 0,
    alerts24h: alertCount?.total ?? 0,
    asOf: now,
  };
}

