# 07 — Implementation Phases

Never silently skip a phase. Each phase ends with verification and a handoff.

## 00 Foundation
Repository structure, Docker Compose skeleton, environment, docs/progress, basic test commands.
Exit: setup documented, checks exist, local foundation works.

## 01 Database
Drizzle, PostgreSQL, schema, migrations, seed/demo data.
Exit: clean migration and CRUD smoke tests.

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
FastAPI, health endpoint, contracts, Ollama adapter, output schema.
Exit: model adapter configurable; invalid output rejected.

## 07 Agent Tools
Five typed read-only tools, bounds and tests.
Exit: no arbitrary SQL/shell/network mutation.

## 08 LangGraph Investigation
Graph, state, bounded loops, trace persistence.
Exit: demo incident investigation completes and trace is inspectable.

## 09 RAG / MITRE
Document ingestion, embeddings, Qdrant, MITRE retrieval and source references.
Exit: retrieval smoke tests with source IDs.

## 10 Evidence-Grounded Verdict
Prompt, schema validation, evidence reference validation, review path.
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
