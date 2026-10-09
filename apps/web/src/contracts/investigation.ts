// The AI service owns these contracts (D-059); the web side validates what crosses the boundary (D-011).
import { z } from "zod";
import { INCIDENT_ID, RUN_ID } from "../lib/ids.ts";

export const investigationRequest = z.strictObject({
  incident_id: z.string().regex(INCIDENT_ID),
  requested_by: z.string().regex(/^an_[0-9a-f]{16}$/),
});

export const investigationAccepted = z.strictObject({
  investigation_run_id: z.string().regex(RUN_ID),
  status: z.literal("queued"),
});
