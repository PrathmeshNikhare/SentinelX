import { NextResponse } from "next/server";
import { apiError, withSession } from "@/server/api";
import { getInvestigation } from "@/server/queries/investigations";

// Investigation status, verdict, trace and evidence (D-015, D-018); the UI polls this.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  return withSession("GET /api/investigations/:id", async () => {
    const investigation = await getInvestigation((await params).id);
    return investigation ? NextResponse.json({ investigation }) : apiError(404, "not_found", "Investigation not found.");
  });
}
