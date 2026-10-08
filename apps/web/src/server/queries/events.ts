import "server-only";
import { desc } from "drizzle-orm";
import { securityEvents } from "../../db/schema.ts";
import { db } from "../db.ts";

const MAX_EVENTS = 100;

export async function listRecentEvents(limit = MAX_EVENTS) {
  return db()
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
    .from(securityEvents)
    .orderBy(desc(securityEvents.occurredAt))
    .limit(Math.min(limit, MAX_EVENTS));
}
