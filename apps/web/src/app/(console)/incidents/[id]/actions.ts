"use server";

import { revalidatePath } from "next/cache";
import { isIncidentStatus } from "@/lib/incident-lifecycle";
import { requireSession } from "@/server/auth/session";
import { logEvent } from "@/server/log";
import { transitionIncident } from "@/server/queries/incidents";

/** Lifecycle buttons on the incident page (D-054). The same atomic transition as PATCH /api/incidents/:id. */
export async function changeIncidentStatus(formData: FormData): Promise<void> {
  const session = await requireSession();
  if (!session) throw new Error("The database is unavailable.");
  const id = formData.get("incidentId");
  const to = formData.get("status");
  if (typeof id !== "string" || !isIncidentStatus(to)) throw new Error("Invalid status change.");
  const result = await transitionIncident(id, to);
  if (result.ok) {
    logEvent("incident.status_changed", { incidentId: id, analystId: session.analystId, from: result.from, to: result.to });
  }
  // An invalid transition (e.g. a stale page) simply re-renders with the current status and its valid actions.
  revalidatePath(`/incidents/${id}`);
}
