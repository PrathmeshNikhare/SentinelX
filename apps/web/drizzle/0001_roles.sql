-- Least-privilege roles (D-022, D-031). Roles are cluster-wide and NOLOGIN; the phase that first
-- connects as a role adds LOGIN and a password from the environment. No DELETE/TRUNCATE is granted.
-- Tables added by later migrations must grant explicitly.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sentinelx_app') THEN
    CREATE ROLE sentinelx_app NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sentinelx_ai_tools') THEN
    CREATE ROLE sentinelx_ai_tools NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sentinelx_ai_writer') THEN
    CREATE ROLE sentinelx_ai_writer NOLOGIN;
  END IF;
END
$$;
--> statement-breakpoint
GRANT USAGE ON SCHEMA public TO sentinelx_app, sentinelx_ai_tools, sentinelx_ai_writer;
--> statement-breakpoint
-- Web + detection worker: read everything, write the detection/incident pipeline and analyst accounts.
GRANT SELECT ON
  analysts, security_events, detection_signals, alerts, incidents, incident_events, incident_alerts,
  investigation_runs, investigation_trace, evidence, knowledge_documents, ip_reputation, mitre_techniques
TO sentinelx_app;
--> statement-breakpoint
GRANT INSERT, UPDATE ON
  analysts, security_events, detection_signals, alerts, incidents, incident_events, incident_alerts
TO sentinelx_app;
--> statement-breakpoint
-- Agent tools: SELECT-only, and never analysts (password hashes) or investigation records.
GRANT SELECT ON
  security_events, detection_signals, alerts, incidents, incident_events, incident_alerts,
  knowledge_documents, ip_reputation, mitre_techniques
TO sentinelx_ai_tools;
--> statement-breakpoint
-- AI service persistence: load incidents, update run status, append-only trace and evidence.
GRANT SELECT ON
  security_events, detection_signals, alerts, incidents, incident_events, incident_alerts,
  investigation_runs, investigation_trace, evidence
TO sentinelx_ai_writer;
--> statement-breakpoint
GRANT INSERT, UPDATE ON investigation_runs TO sentinelx_ai_writer;
--> statement-breakpoint
GRANT INSERT ON investigation_trace, evidence TO sentinelx_ai_writer;
