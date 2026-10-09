import "server-only";
import { investigationAccepted, investigationRequest } from "../contracts/investigation.ts";
import { logError } from "./log.ts";

const TIMEOUT_MS = 5_000; // the AI service answers 202 before running the graph (D-015)
const MIN_TOKEN_LENGTH = 32; // as the AI service enforces (D-058)

export type StartInvestigationResult =
  | { ok: true; runId: string }
  | { ok: false; reason: "not_found" | "in_progress" | "unavailable" };

/** Asks the internal AI service to queue an investigation (D-015, D-022). Service failures never throw; malformed IDs do. */
export async function startInvestigation(
  incidentId: string,
  analystId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<StartInvestigationResult> {
  const baseUrl = process.env.AI_SERVICE_URL;
  const token = process.env.AI_SERVICE_TOKEN;
  if (!baseUrl || !token || token.length < MIN_TOKEN_LENGTH) {
    logError("ai.misconfigured", new Error("AI_SERVICE_URL or AI_SERVICE_TOKEN is missing or too short"));
    return { ok: false, reason: "unavailable" };
  }
  const body = investigationRequest.parse({ incident_id: incidentId, requested_by: analystId });
  let response: Response;
  try {
    response = await fetchImpl(new URL("/v1/investigations", baseUrl), {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify(body),
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (error) {
    logError("ai.unreachable", error);
    return { ok: false, reason: "unavailable" };
  }
  if (response.status === 404) return { ok: false, reason: "not_found" };
  if (response.status === 409) return { ok: false, reason: "in_progress" };
  if (response.status !== 202) {
    logError("ai.unexpected_status", new Error(`AI service returned HTTP ${response.status}`));
    return { ok: false, reason: "unavailable" };
  }
  const accepted = investigationAccepted.safeParse(await response.json().catch(() => null));
  if (!accepted.success) {
    logError("ai.contract_violation", new Error("investigation-accepted response does not match its contract"));
    return { ok: false, reason: "unavailable" };
  }
  return { ok: true, runId: accepted.data.investigation_run_id };
}
