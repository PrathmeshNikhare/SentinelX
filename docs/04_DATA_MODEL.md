# 04 — Data Model

Use PostgreSQL + Drizzle. Drizzle migrations are the only source of DDL (D-010).

Core tables:
- `analysts`: id, email, name, password_hash, created_at. Console login accounts only (D-012).
- `security_events`: id, external_event_id (unique), timestamp, user_id, source_ip, event_type, action, resource, status, metadata_json, created_at. `user_id` is a monitored external identity with no foreign key to `analysts`.
- `detection_signals`: id, event_id, rule_name (required), rule_score, severity, reason, created_at. Rule hits only (D-021).
- `alerts`: id, event_id (unique), risk_score, anomaly_score, model_version, severity, reasons_json, created_at.
- `incidents`: id, title, status, risk_score, severity, primary_user_id, primary_ip, started_at, updated_at, created_at
- `incident_events`: incident_id, event_id
- `incident_alerts`: incident_id, alert_id
- `investigation_runs`: id, incident_id, status (`queued|running|completed|failed`), started_at, completed_at, requires_review, verdict_json (accepted verdict only), raw_output_json, validation_errors_json, model_name, prompt_version, error_message (D-015, D-019)
- `investigation_trace`: id, investigation_run_id, step_index, action_type, action_origin (`llm|fallback`), tool_name, input_json, result_json, evidence_ids_json, retrieval_refs_json, created_at
- `evidence`: id, investigation_run_id, source_type (`event|alert|user_history|ip_reputation|related_logs|mitre|knowledge`), source_id, claim, data_json, created_at (D-018)
- `knowledge_documents`: id, source, external_id, title, content_hash, qdrant_point_id, metadata_json, created_at
- `ip_reputation`: ip, reputation (`known_good|unknown|suspicious|malicious`), score, tags_json, source, updated_at. Synthetic local data (D-020).
- `mitre_techniques`: technique_id, name, tactics_json, description, attack_version. Curated local subset (D-020).

Add foreign keys and deliberate indexes for timestamp, user_id, source_ip, incident status. Use JSON only for genuinely flexible metadata.

Database roles (D-022): a migration role (DDL), an application role for web and detection, a SELECT-only role for agent tools, and an AI persistence role limited to INSERT/UPDATE on `investigation_runs`, `investigation_trace` and `evidence`.
