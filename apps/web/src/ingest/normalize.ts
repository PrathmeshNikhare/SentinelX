// Pure normalization of a validated API event into the Kafka message shape (D-043).
import { SCHEMA_VERSION, type NormalizedEvent, type SecurityEventInput } from "../contracts/security-event.ts";

export const MAX_FUTURE_SKEW_MS = 5 * 60 * 1000;

export interface ValidationIssue {
  path: string;
  message: string;
}

export type NormalizeResult = { ok: true; event: NormalizedEvent } | { ok: false; issues: ValidationIssue[] };

/** Canonical IP text: compressed lowercase IPv6, and IPv4-mapped IPv6 (::ffff:a.b.c.d) as plain IPv4. */
export function canonicalIp(ip: string): string {
  if (!ip.includes(":")) return ip;
  const canonical = new URL(`http://[${ip}]`).hostname.slice(1, -1);
  const mapped = /^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(canonical);
  if (!mapped?.[1] || !mapped[2]) return canonical;
  const high = Number.parseInt(mapped[1], 16);
  const low = Number.parseInt(mapped[2], 16);
  return [high >> 8, high & 255, low >> 8, low & 255].join(".");
}

export function normalizeEvent(input: SecurityEventInput, now: Date): NormalizeResult {
  const occurredAt = new Date(input.timestamp);
  if (occurredAt.getTime() > now.getTime() + MAX_FUTURE_SKEW_MS) {
    return { ok: false, issues: [{ path: "timestamp", message: "must not be more than 5 minutes in the future" }] };
  }
  return {
    ok: true,
    event: {
      schema_version: SCHEMA_VERSION,
      event_id: input.event_id,
      occurred_at: occurredAt.toISOString(),
      ingested_at: now.toISOString(),
      user_id: input.user_id.toLowerCase(),
      source_ip: canonicalIp(input.source_ip),
      event_type: input.event_type,
      action: input.action.toLowerCase(),
      resource: input.resource.trim(),
      status: input.status,
      metadata: input.metadata ?? {},
    },
  };
}
