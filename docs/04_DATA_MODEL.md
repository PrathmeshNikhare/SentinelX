# 04 — Data Model

Use PostgreSQL + Drizzle. Drizzle migrations are the only source of DDL (D-010). Source of truth: `apps/web/src/db/schema.ts` and `apps/web/drizzle/`.

IDs are database-generated prefixed text (D-030), e.g. `inc_3f9a2b1c4d5e6f70`. Timestamps are `timestamptz` (UTC). Enums: `severity` (`LOW|MEDIUM|HIGH|CRITICAL`), `incident_status` (`open|investigating|resolved`), `investigation_run_status`, `action_origin`, `evidence_source_type`, `reputation_level`.

Core tables:
- `analysts` (`an_`): id, email (unique, lowercase), name, password_hash (scrypt, D-034), created_at. Console login accounts only (D-012).
- `analyst_sessions` (`ses_`): id, analyst_id, token_hash (SHA-256 of the cookie token, unique), created_at, expires_at, revoked_at (D-034).
- `security_events` (`se_`): id, external_event_id (unique), occurred_at, user_id, source_ip (inet), event_type, action, resource, status, metadata_json, created_at. `user_id` is a monitored external identity with no foreign key to `analysts`. The API field `timestamp` maps to `occurred_at`.
- `detection_signals` (`sig_`): id, event_id, rule_name (required), rule_score (0–100), severity, reason, created_at; unique (event_id, rule_name). Rule hits only (D-021).
- `alerts` (`alt_`): id, event_id (unique), risk_score (0–100), anomaly_score, model_version, severity, reasons_json, created_at.
- `incidents` (`inc_`): id, title, status (default `open`), risk_score (0–100), severity, primary_user_id, primary_ip (inet), started_at, updated_at, created_at
- `incident_events`: incident_id, event_id (composite PK)
- `incident_alerts`: incident_id, alert_id (composite PK)
- `investigation_runs` (`run_`): id, incident_id, status (default `queued`), requires_review (default false), verdict_json (accepted verdict only), raw_output_json (`{attempts: [{valid, output | raw, error?, findings}]}`), validation_errors_json (`[{attempt, code, detail, effect}]`), model_name, prompt_version, error_message, started_at, completed_at, created_at (D-015, D-019, D-073)
- `investigation_trace` (`trc_`): id, investigation_run_id, step_index (≥0, unique per run), action_type, action_origin (`llm|fallback`, null for system nodes), tool_name, input_json, result_json, evidence_ids_json, retrieval_refs_json, created_at
- `evidence` (`ev_`): id, investigation_run_id, source_type, source_id, claim, data_json, created_at (D-018)
- `knowledge_documents` (`kd_`): id, source, external_id, title, content_hash, qdrant_point_id, metadata_json, created_at; unique (source, external_id)
- `ip_reputation`: ip (inet PK), reputation, score (0 benign – 100 malicious), tags_json, source, updated_at. Synthetic local data (D-020).
- `mitre_techniques`: technique_id (PK, `T####` or `T####.###`), name, tactics_json, description, attack_version. Curated local subset (D-020).

Foreign keys connect every child to its parent; no cascading deletes (audit data is preserved). Indexes: `security_events` (occurred_at), (user_id, occurred_at), (source_ip, occurred_at); `incidents` (status, updated_at); `detection_signals`/`alerts` via their unique keys; link tables on the second column; `investigation_runs` (incident_id); `evidence` (investigation_run_id); `knowledge_documents` (content_hash). JSON only for genuinely flexible metadata.

## Database roles (D-022, D-031)
`npm run db:roles` enables LOGIN for `sentinelx_app` (Phase 02), `sentinelx_ai_tools` (Phase 07, D-061) and `sentinelx_ai_writer` (Phase 08, D-065). No role has DELETE, TRUNCATE or CREATE.

| Role | SELECT | INSERT/UPDATE |
|---|---|---|
| owner (`POSTGRES_USER`) | all; runs migrations and seeds | all |
| `sentinelx_app` (web + detection; LOGIN via `npm run db:roles`, D-035) | all tables | analysts, analyst_sessions, security_events, detection_signals, alerts, incidents, incident_events, incident_alerts |
| `sentinelx_ai_tools` (agent tools; LOGIN via `npm run db:roles`, D-061) | security_events, detection_signals, alerts, incidents, incident links, knowledge_documents, ip_reputation, mitre_techniques | none |
| `sentinelx_ai_writer` (investigation runs, trace, evidence; LOGIN via `npm run db:roles`, D-065) | pipeline tables + investigation_runs, investigation_trace, evidence | INSERT/UPDATE investigation_runs; INSERT only investigation_trace, evidence |

Reference data (`ip_reputation`, `mitre_techniques`, `knowledge_documents`) is written by the owner through seed/ingestion scripts.
