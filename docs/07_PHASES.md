# 07 — Implementation Phases

Never silently skip a phase. Each phase ends with verification and a handoff.

## 00 Foundation
Repository structure (D-009), Docker Compose infrastructure (D-023), environment, docs/progress, basic test commands and the verification entrypoint (D-024). No application code.

Exit (every item must be shown with command output):
1. Directories `apps/web/`, `services/detection/`, `services/ai/`, `contracts/v1/`, `fixtures/`, `scripts/` exist, each with a README stating owner and the phase that fills it.
2. `docker compose config --quiet` exits 0.
3. `docker compose up -d` starts `postgres`, `kafka` (KRaft) and `qdrant`, and `docker compose ps` shows all three `healthy` within 120 s, using healthchecks defined in the Compose file.
4. From the host: PostgreSQL accepts a connection with `.env.example` credentials; Kafka topic `security-events` exists (created idempotently by a script) and is listed via `localhost:9092`; Qdrant `GET http://localhost:6333/readyz` returns 200.
5. `python scripts/verify.py` (stdlib only) runs every available check: Compose config, service health/connectivity from item 4, a Vitest smoke test with `tsc --noEmit` and ESLint, and for each Python service a pytest smoke test with ruff and mypy. It prints PASS/FAIL per check and exits 0. Ollama (`GET http://localhost:11434/api/tags`) is reported as WARN, not FAIL, until Phase 06.
6. `docker compose down` followed by `python scripts/verify.py` reports the infrastructure checks as FAIL with a non-zero exit (the checks are real).
7. `git ls-files` lists no `.env` and no `node_modules/` or `.venv/` content; every variable referenced by `docker-compose.yml` is present in `.env.example`.
8. `docs/16_ENVIRONMENT.md` lists exact tool versions and setup steps from a clean clone for Windows (PowerShell) and POSIX shells; README has a quickstart that ends with `python scripts/verify.py`.
9. No Drizzle schema, Next.js pages/routes, FastAPI routes, Kafka producer/consumer or detection logic exists (Reviewer confirms by inspection).
10. `/verify-phase` returns APPROVED, `/handoff` writes `progress/handoffs/phase-00.md`, and STATUS.md, PHASE_LOG.md and CURRENT_HANDOFF.md are updated and committed.

## 01 Database
Drizzle, PostgreSQL, schema (docs/04), migrations, database roles (D-022, D-031), and reference data seeded from `fixtures/`: `ip_reputation` and `mitre_techniques` (D-020). Demo events come from the Phase 03 generator, not a seed (D-032).
Exit: clean migration from an empty DB, CRUD smoke tests, role permission tests (tool role cannot write).

## 02 Web Shell
Next.js App Router, auth boundary, navigation, incident list/detail shell, API placeholders.
Exit: UI runs; loading/error/empty states; no fake metrics.

## 03 Event Ingestion
Event schema, normalization, API ingestion, Kafka producer, controlled demo generator.
Exit: event travels into Kafka; validation tests pass.

## 04 Detection Engine
Rules, features, Isolation Forest, deterministic risk engine.
Exit: scenarios produce expected signals; risk unit tests pass.

## 05 Correlation & Incidents
Alert persistence, bounded correlation, incident lifecycle.
Exit: expected incidents; duplicate/correlation tests.

## 06 AI Service Foundation
FastAPI, health endpoint, internal auth (`AI_SERVICE_TOKEN`), contracts, Ollama adapter, verdict Pydantic schema.
Exit: model adapter configurable; schema-invalid output rejected; unauthenticated calls rejected.

## 07 Agent Tools
Five typed read-only tools, bounds and tests. `search_security_knowledge` is built against a retriever interface and tested with a fake (D-026).
Exit: no arbitrary SQL/shell/network mutation; tools run under the SELECT-only role.

## 08 LangGraph Investigation
Graph, state, bounded loops, trace persistence.
Exit: demo incident investigation completes asynchronously with a schema-valid verdict (Phase 06 schema) and an inspectable trace. Evidence-ID validation arrives in Phase 10.

## 09 RAG / MITRE
Document ingestion, embeddings, Qdrant, MITRE retrieval and source references.
Exit: retrieval smoke tests with source IDs.

## 10 Evidence-Grounded Verdict
Hardened prompt, evidence-ID and MITRE-ID validation, severity-disagreement rule (D-016), review path and raw-output audit storage (D-019).
Exit: supported claims cite evidence; unsupported references force review.

## 11 Incident UI
Timeline, signals, evidence, MITRE, trace, verdict and recommendations.
Exit: complete attack scenario understandable without source code.

## 12 Security & Reliability
Auth hardening, secrets, input validation, audit logging, dependency review, failure handling.
Exit: security checklist passes.

## 13 Testing & Demo
Unit, integration, E2E, demo fixtures, README and demo instructions.
Exit: clean-machine setup and demo are reproducible.

## 14 Interview Polish
Architecture diagram, tradeoffs, performance notes, limitations and interview Q&A.
Exit: every major component has a defensible why.
