# 01 — Requirements

## Goal
SentinelX ingests security events, detects suspicious activity using deterministic rules and anomaly detection, correlates signals into incidents, and investigates incidents using an evidence-grounded read-only LangGraph agent.

## Functional requirements
- Event ingestion: normalized JSON/CSV/demo events with event_id, timestamp, user_id, source_ip, event_type, action, resource, status, metadata.
- Detection: repeated failed logins, unusual successful login, suspicious PowerShell, sensitive file access, privilege escalation, impossible travel where sufficient data exists, suspicious event chains.
- Anomaly detection: Isolation Forest over documented features; output is an anomaly signal, not final risk.
- Risk engine: deterministic 0–100 score from rule score, anomaly score, event severity, IP reputation and correlation/context. Levels LOW 0–29, MEDIUM 30–59, HIGH 60–79, CRITICAL 80–100.
- Correlation: bounded user/IP/category/time-window correlation.
- Investigation: LangGraph workflow with typed read-only tools.
- Tools: get_user_history, get_ip_reputation, get_related_logs, get_mitre_technique, search_security_knowledge.
- RAG: Qdrant retrieval of approved security knowledge/MITRE data.
- Verdict: verdict, confidence, severity, summary, evidence_ids, MITRE techniques, recommendations.
- Trace: action/tool, input summary, result summary, evidence IDs, retrieval refs, timestamps. Never persist hidden chain-of-thought.
- Dashboard: overview, incidents, incident detail, timeline, signals, evidence, MITRE and investigation trace.

## Non-functional
Local-first, Docker Compose, reproducible tests, graceful failures, bounded tools, schema validation, no secrets in git, usable on a laptop.

## Out of scope
Enterprise SIEM integrations, autonomous remediation, production-scale Kafka operations, Kubernetes, cloud deployment, real blocking/quarantine, fine-tuning, multi-agent swarm.
