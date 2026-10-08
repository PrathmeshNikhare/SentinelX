# 04 — Data Model

Use PostgreSQL + Drizzle.

Core tables:
- `users`: id, email, name, password_hash, created_at
- `security_events`: id, external_event_id, timestamp, user_id, source_ip, event_type, action, resource, status, metadata_json, created_at
- `detection_signals`: id, event_id, rule_name, rule_score, anomaly_score, severity, reason, created_at
- `alerts`: id, event_id, risk_score, severity, reasons_json, created_at
- `incidents`: id, title, status, risk_score, severity, primary_user_id, primary_ip, started_at, updated_at, created_at
- `incident_events`: incident_id, event_id
- `investigation_runs`: id, incident_id, status, started_at, completed_at, requires_review, verdict_json
- `investigation_trace`: id, investigation_run_id, step_index, action_type, tool_name, input_json, result_json, evidence_ids_json, retrieval_refs_json, created_at
- `knowledge_documents`: id, source, external_id, title, content_hash, qdrant_point_id, metadata_json, created_at
- `evidence`: id, investigation_run_id, source_type, source_id, claim, data_json, created_at

Add foreign keys and deliberate indexes for timestamp, user_id, source_ip, incident status. Use JSON only for genuinely flexible metadata.
