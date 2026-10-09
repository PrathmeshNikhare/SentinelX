import "server-only";
import { asc, desc, eq } from "drizzle-orm";
import { evidence, incidents, investigationRuns, investigationTrace } from "../../db/schema.ts";
import { isIncidentId, isRunId } from "../../lib/ids.ts";
import { db } from "../db.ts";

const MAX_TRACE_STEPS = 100; // a run has at most 2 steps per tool call (budget 8) plus 3 (D-064)
const MAX_EVIDENCE = 200;

// raw_output_json (D-019 audit copy of every model answer) is not served here; it is stored for review tooling.
const runColumns = {
  id: investigationRuns.id,
  incidentId: investigationRuns.incidentId,
  status: investigationRuns.status,
  requiresReview: investigationRuns.requiresReview,
  verdict: investigationRuns.verdictJson,
  validationErrors: investigationRuns.validationErrorsJson,
  modelName: investigationRuns.modelName,
  promptVersion: investigationRuns.promptVersion,
  errorMessage: investigationRuns.errorMessage,
  createdAt: investigationRuns.createdAt,
  startedAt: investigationRuns.startedAt,
  completedAt: investigationRuns.completedAt,
};

export async function incidentExists(id: string): Promise<boolean> {
  if (!isIncidentId(id)) return false;
  const [row] = await db().select({ id: incidents.id }).from(incidents).where(eq(incidents.id, id)).limit(1);
  return row !== undefined;
}

/** Run with its trace and evidence, or null if the id is malformed or unknown. */
export async function getInvestigation(id: string) {
  if (!isRunId(id)) return null;
  const [run] = await db().select(runColumns).from(investigationRuns).where(eq(investigationRuns.id, id)).limit(1);
  if (!run) return null;
  const trace = await db()
    .select({
      stepIndex: investigationTrace.stepIndex,
      actionType: investigationTrace.actionType,
      actionOrigin: investigationTrace.actionOrigin,
      toolName: investigationTrace.toolName,
      input: investigationTrace.inputJson,
      result: investigationTrace.resultJson,
      evidenceIds: investigationTrace.evidenceIdsJson,
      retrievalRefs: investigationTrace.retrievalRefsJson,
      createdAt: investigationTrace.createdAt,
    })
    .from(investigationTrace)
    .where(eq(investigationTrace.investigationRunId, id))
    .orderBy(asc(investigationTrace.stepIndex))
    .limit(MAX_TRACE_STEPS);
  const items = await db()
    .select({
      id: evidence.id,
      sourceType: evidence.sourceType,
      sourceId: evidence.sourceId,
      claim: evidence.claim,
      data: evidence.dataJson,
      createdAt: evidence.createdAt,
    })
    .from(evidence)
    .where(eq(evidence.investigationRunId, id))
    .orderBy(asc(evidence.createdAt), asc(evidence.id))
    .limit(MAX_EVIDENCE);
  return { ...run, trace, evidence: items };
}

/** Most recent run of an incident (for the incident page), or null. */
export async function latestInvestigation(incidentId: string) {
  if (!isIncidentId(incidentId)) return null;
  const [run] = await db()
    .select(runColumns)
    .from(investigationRuns)
    .where(eq(investigationRuns.incidentId, incidentId))
    .orderBy(desc(investigationRuns.createdAt))
    .limit(1);
  return run ?? null;
}
