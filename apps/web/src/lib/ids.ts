// Database-generated IDs (D-030): validate at the boundary before querying.
export const INCIDENT_ID = /^inc_[0-9a-f]{16}$/;
export const isIncidentId = (value: string): boolean => INCIDENT_ID.test(value);
export const RUN_ID = /^run_[0-9a-f]{16}$/;
export const isRunId = (value: string): boolean => RUN_ID.test(value);
