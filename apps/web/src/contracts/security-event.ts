// Event contracts v1 (D-042, D-043). Source of truth for contracts/v1/*.schema.json (`npm run contracts:generate`).
import { z } from "zod";

export const SCHEMA_VERSION = "v1";
export const MAX_METADATA_BYTES = 4096;
export const MAX_BODY_BYTES = 16 * 1024;

export const EVENT_TYPES = ["authentication", "process", "file_access", "privilege_change", "network"] as const;
export const EVENT_STATUSES = ["success", "failed"] as const;

const FORBIDDEN_METADATA_KEYS = new Set(["__proto__", "constructor", "prototype"]);
// No ASCII control characters (newlines, NUL, escape sequences) in free-text fields.
// eslint-disable-next-line no-control-regex -- matching control characters is the point: they are rejected
const NO_CONTROL_CHARS = /^[^\u0000-\u001f\u007f]+$/;

const eventId = z
  .string()
  .regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/, "1-128 chars: letters, digits, _ . : - (starting with a letter or digit)");
const userId = z
  .string()
  .regex(/^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$/, "1-128 chars: letters, digits, _ . @ - (starting with a letter or digit)");
const sourceIp = z.union([z.ipv4(), z.ipv6()]);
const eventType = z.enum(EVENT_TYPES);
const eventStatus = z.enum(EVENT_STATUSES);
const action = z.string().regex(/^[A-Za-z0-9_.-]{1,64}$/, "1-64 chars: letters, digits, _ . -");
const resource = z.string().min(1).max(512).regex(NO_CONTROL_CHARS, "must not contain control characters");

// Keys are checked by the key schema, i.e. on the raw input: on zod's output a `__proto__` key would already have
// become the object's prototype and be invisible. Values are JSON (the body comes from JSON.parse), so `unknown` is exact.
const metadataKey = z
  .string()
  .min(1)
  .max(64)
  .refine((key) => !FORBIDDEN_METADATA_KEYS.has(key), { message: "reserved key name is not allowed" });
const metadata = z
  .record(metadataKey, z.unknown())
  .superRefine((value, ctx) => {
    if (new TextEncoder().encode(JSON.stringify(value)).length > MAX_METADATA_BYTES) {
      ctx.addIssue({ code: "custom", message: `must serialize to at most ${MAX_METADATA_BYTES} bytes` });
    }
  })
  .meta({ description: `Free-form JSON object, keys 1-64 chars, serialized size <= ${MAX_METADATA_BYTES} bytes.` });

/** Body of POST /api/events (docs/14). Unknown fields are rejected. */
export const securityEventInput = z
  .strictObject({
    event_id: eventId,
    timestamp: z.iso.datetime({ offset: true }).meta({ description: "ISO 8601 with offset, e.g. 2026-01-01T10:00:00Z" }),
    user_id: userId,
    source_ip: sourceIp,
    event_type: eventType,
    action,
    resource,
    status: eventStatus,
    metadata: metadata.optional(),
  })
  .meta({ title: "SentinelX security event (API input) v1" });

/** Message value on Kafka topic `security-events` (D-043). */
export const normalizedEvent = z
  .strictObject({
    schema_version: z.literal(SCHEMA_VERSION),
    event_id: eventId,
    occurred_at: z.iso.datetime().meta({ description: "UTC, ISO 8601 with Z" }),
    ingested_at: z.iso.datetime().meta({ description: "UTC, ISO 8601 with Z" }),
    user_id: userId.regex(/^[^A-Z]*$/, "lowercase"),
    source_ip: sourceIp,
    event_type: eventType,
    action: action.regex(/^[^A-Z]*$/, "lowercase"),
    resource,
    status: eventStatus,
    metadata,
  })
  .meta({ title: "SentinelX normalized security event (Kafka message) v1" });

export type SecurityEventInput = z.infer<typeof securityEventInput>;
export type NormalizedEvent = z.infer<typeof normalizedEvent>;
