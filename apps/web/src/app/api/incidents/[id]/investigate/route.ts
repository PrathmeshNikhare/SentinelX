import { NextResponse } from "next/server";
import { apiError, withSession } from "@/server/api";
import { startInvestigation } from "@/server/ai-service";
import { logEvent } from "@/server/log";
import { incidentExists } from "@/server/queries/investigations";

// Starts an asynchronous investigation (D-015): 202 {investigation_run_id}; poll GET /api/investigations/:id.
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  return withSession("POST /api/incidents/:id/investigate", async (session) => {
    const id = (await params).id;
    if (!(await incidentExists(id))) return apiError(404, "not_found", "Incident not found.");
    const result = await startInvestigation(id, session.analystId);
    if (result.ok) {
      logEvent("investigation.requested", { incidentId: id, runId: result.runId, analystId: session.analystId });
      return NextResponse.json({ investigation_run_id: result.runId }, { status: 202 });
    }
    if (result.reason === "not_found") return apiError(404, "not_found", "Incident not found.");
    if (result.reason === "in_progress") {
      return apiError(409, "investigation_in_progress", "An investigation of this incident is already running.");
    }
    return apiError(503, "unavailable", "The AI service is unavailable.");
  });
}
