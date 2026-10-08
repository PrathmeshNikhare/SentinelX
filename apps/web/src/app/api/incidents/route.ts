import { NextResponse } from "next/server";
import { withSession } from "@/server/api";
import { listIncidents } from "@/server/queries/incidents";

export async function GET(): Promise<Response> {
  return withSession("GET /api/incidents", async () => NextResponse.json({ incidents: await listIncidents() }));
}
