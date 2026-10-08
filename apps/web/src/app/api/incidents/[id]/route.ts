import { NextResponse } from "next/server";
import { apiError, withSession } from "@/server/api";
import { getIncident } from "@/server/queries/incidents";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  return withSession("GET /api/incidents/:id", async () => {
    const incident = await getIncident((await params).id);
    return incident ? NextResponse.json({ incident }) : apiError(404, "not_found", "Incident not found.");
  });
}
