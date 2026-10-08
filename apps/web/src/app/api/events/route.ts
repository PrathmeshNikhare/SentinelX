// POST /api/events (docs/14, D-041, D-043): authenticate, size-limit, parse, validate, normalize, publish to Kafka.
// The API does not write to PostgreSQL; the detection worker persists and deduplicates events (D-014).
import { NextResponse } from "next/server";
import type { z } from "zod";
import { MAX_BODY_BYTES, securityEventInput } from "@/contracts/security-event";
import { parseJsonBody, readBodyLimited } from "@/ingest/body";
import { eventProducer } from "@/ingest/kafka";
import { normalizeEvent, type ValidationIssue } from "@/ingest/normalize";
import { apiError, withIngestAuth } from "@/server/api";
import { logError, logEvent } from "@/server/log";

const ROUTE = "POST /api/events";

const toIssues = (error: z.ZodError): ValidationIssue[] =>
  error.issues.slice(0, 20).map((issue) => ({
    path: issue.path.map(String).join(".") || "(root)",
    message: issue.message.slice(0, 200),
  }));

const validationFailed = (issues: ValidationIssue[]) =>
  apiError(400, "validation_failed", "The event does not match contract security-event v1.", { issues });

export async function POST(request: Request): Promise<Response> {
  return withIngestAuth(ROUTE, request, async (auth) => {
    const contentType = request.headers.get("content-type") ?? "";
    if (!/^application\/json(\s*;|$)/i.test(contentType)) {
      return apiError(415, "unsupported_media_type", "Content-Type must be application/json.");
    }
    const body = await readBodyLimited(request, MAX_BODY_BYTES);
    if (!body.ok) return apiError(413, "payload_too_large", `The body must be at most ${MAX_BODY_BYTES} bytes.`);

    const json = parseJsonBody(body.text);
    if (!json.ok) {
      return json.reason === "invalid_json"
        ? apiError(400, "invalid_json", "The body must be valid JSON.")
        : validationFailed([{ path: "(body)", message: 'the key "__proto__" is not allowed' }]);
    }
    const parsed = securityEventInput.safeParse(json.value);
    if (!parsed.success) return validationFailed(toIssues(parsed.error));
    const normalized = normalizeEvent(parsed.data, new Date());
    if (!normalized.ok) return validationFailed(normalized.issues);

    const { event } = normalized;
    try {
      await eventProducer().publish(event);
    } catch (error) {
      logError("ingest.publish_failed", error, { route: ROUTE, eventId: event.event_id });
      return apiError(503, "unavailable", "The event could not be queued. Retry later.");
    }
    logEvent("ingest.accepted", { eventId: event.event_id, eventType: event.event_type, auth });
    return NextResponse.json({ event_id: event.event_id, status: "accepted" }, { status: 202 });
  });
}
