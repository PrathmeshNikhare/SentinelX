import { NextResponse } from "next/server";
import { parseJsonBody, readBodyLimited } from "@/ingest/body";
import { isIncidentStatus } from "@/lib/incident-lifecycle";
import { apiError, withSession } from "@/server/api";
import { logEvent } from "@/server/log";
import { getIncident, transitionIncident } from "@/server/queries/incidents";

const MAX_PATCH_BYTES = 1024;

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  return withSession("GET /api/incidents/:id", async () => {
    const incident = await getIncident((await params).id);
    return incident ? NextResponse.json({ incident }) : apiError(404, "not_found", "Incident not found.");
  });
}

/** Lifecycle change (D-054): body {"status": "open" | "investigating" | "resolved"}. */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  return withSession("PATCH /api/incidents/:id", async (session) => {
    if (!/^application\/json(\s*;|$)/i.test(request.headers.get("content-type") ?? "")) {
      return apiError(415, "unsupported_media_type", "Content-Type must be application/json.");
    }
    const body = await readBodyLimited(request, MAX_PATCH_BYTES);
    if (!body.ok) return apiError(413, "payload_too_large", `The body must be at most ${MAX_PATCH_BYTES} bytes.`);
    const json = parseJsonBody(body.text);
    const value: unknown = json.ok ? json.value : null;
    const keys = value && typeof value === "object" && !Array.isArray(value) ? Object.keys(value) : [];
    const status = keys.length === 1 && keys[0] === "status" ? (value as { status: unknown }).status : undefined;
    if (!isIncidentStatus(status)) {
      return apiError(400, "validation_failed", 'Body must be {"status": "open" | "investigating" | "resolved"}.');
    }

    const id = (await params).id;
    const result = await transitionIncident(id, status);
    if (!result.ok && result.reason === "not_found") return apiError(404, "not_found", "Incident not found.");
    if (!result.ok) {
      return apiError(409, "invalid_transition", `Cannot change status from ${result.current} to ${status}.`, {
        current: result.current,
      });
    }
    logEvent("incident.status_changed", { incidentId: id, analystId: session.analystId, from: result.from, to: result.to });
    return NextResponse.json({ incident: { id, status: result.to } });
  });
}
