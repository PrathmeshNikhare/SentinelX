# SentinelX Decisions

### D-001 — Next.js App Router
Use Next.js App Router + TypeScript for the web application.

### D-002 — FastAPI for AI/ML
Use FastAPI for Python-native ML and agent functionality.

### D-003 — Kafka
Use Kafka for event-driven processing and clean ingestion/detection separation.

### D-004 — Deterministic risk score
Risk is calculated by code, not the LLM, for reproducibility and auditability.

### D-005 — Read-only agent
The investigation agent cannot mutate systems.

### D-006 — Qdrant
Qdrant is used for semantic retrieval, not as the operational database.

### D-007 — Ollama
Ollama is the default local LLM runtime.

Add new decisions below. Do not rewrite old decisions without documenting the change.

### D-008 — This directory is the SentinelX repository (2026-10-08)
The harness directory is the repository root (`git init -b main`, baseline commit `fbf08f9`). It is not copied into a separate repo. Parent directories are not part of the project.

### D-009 — Repository layout
```text
apps/web/            Next.js App Router app; Drizzle schema in apps/web/src/db/, migrations in apps/web/drizzle/
services/detection/  Python detection worker (Kafka consumer): normalization, rules, features, Isolation Forest, risk, correlation
services/ai/         Python FastAPI AI service: LangGraph, tools, retrieval, Ollama adapter, verdict validation, trace
contracts/v1/        Versioned cross-service contracts (JSON Schema) + example payloads
fixtures/            Deterministic demo scenarios, synthetic IP reputation, curated MITRE subset, knowledge docs
scripts/             Cross-platform helper scripts (stdlib Python)
docker-compose.yml   Root Compose file
```
Each top-level directory has one owner per `docs/19_AGENT_OWNERSHIP.md`.

### D-010 — Schema authority and Python database access
Drizzle migrations are the only source of DDL. Python services never create or alter tables. Python uses a plain PostgreSQL driver (psycopg 3) with parameterized queries and no ORM. This is a required driver, not a new architectural component: Drizzle is TypeScript-only and two Python services must read/write PostgreSQL.

### D-011 — Cross-service contracts
Payloads crossing a service boundary (event, investigation request/response, verdict) are defined once as JSON Schema in `contracts/v1/` with example payloads. TypeScript and Pydantic models are written to match. Each side has a contract test that parses the shared example payloads. Breaking changes create `contracts/v2/`.

### D-012 — Analysts vs monitored identities
`analysts` (renamed from `users`) holds people who log into the console. `security_events.user_id` is an external monitored identity string (e.g. `user_1`) with no foreign key to `analysts`. The two must never be joined.

### D-013 — Isolation Forest lives in the detection worker
Rules, feature extraction, Isolation Forest scoring, risk and correlation all run in `services/detection/`. FastAPI is the AI investigation service only. This narrows D-002 and resolves the `CLAUDE.md` "FastAPI AI/ML" wording in favor of `docs/02` and `docs/19`. The model is trained by a deterministic script (fixed `random_state`) on a synthetic baseline fixture. It is saved as a versioned artifact with scikit-learn's joblib, and the model version is stored with every alert. The feature list is documented in Phase 04 before training.

### D-014 — Event persistence and idempotency
`POST /api/events` validates and publishes to Kafka. It does not write to PostgreSQL. The detection worker persists `security_events` with a unique `external_event_id` (`ON CONFLICT DO NOTHING`), so duplicate events are idempotent. Kafka message key is `user_id`, to keep per-user ordering for correlation.

### D-015 — Investigations are analyst-initiated and asynchronous
No automatic investigation on incident creation. `POST /api/incidents/:id/investigate` returns `202` with `investigation_run_id`. The AI service runs the graph in a FastAPI background task (no extra queue/broker). The UI polls `GET /api/investigations/:id`. Run status: `queued | running | completed | failed`. `requires_review` is a separate boolean.

### D-016 — Severity and confidence ownership
The deterministic risk engine owns `risk_score` and incident severity. The verdict's `severity` is the model's assessment and is labeled as AI-assessed in the UI. It never overrides the deterministic value. Any difference is recorded as a validation note. A difference of two or more levels (e.g. LOW vs HIGH) sets `requires_review=true`. Verdict `confidence` is model-reported, uncalibrated, bounded to [0, 1], labeled as such and used in no score.

### D-017 — Action selection in the graph
`choose_next_action`: the LLM proposes one action from `available_tools` as structured output. The proposal is validated against the tool's input schema and the step budget. If the proposal is invalid, or Ollama is unavailable, a deterministic fallback plan for the incident type is used. Every choice is traced with its origin (`llm` or `fallback`). Knowledge and MITRE retrieval happen through the `search_security_knowledge` and `get_mitre_technique` tools inside the same loop. There is no separate retrieval node.

### D-018 — Retrieved knowledge is evidence
Every tool result is stored as an `evidence` row, including knowledge chunks (`source_type=knowledge`, `source_id=knowledge_documents.id`) and MITRE lookups (`source_type=mitre`, `source_id=<technique id>`). Every claim in a verdict is therefore cited through `evidence_ids`. The verdict shape in `CLAUDE.md` is unchanged.

### D-019 — Audit storage for rejected verdicts
`investigation_runs.verdict_json` holds only a validated, accepted verdict. Every model output (valid or not) is kept in `raw_output_json`, with `validation_errors_json`, `model_name`, `prompt_version` and `error_message`. A rejected verdict leaves `verdict_json` null and sets `requires_review=true`.

### D-020 — Shared reference data in PostgreSQL
Data used by both detection and the agent lives in PostgreSQL, seeded from `fixtures/` in Phase 01:
- `ip_reputation`: synthetic local reputation, used by the risk engine and `get_ip_reputation`;
- `mitre_techniques`: curated ATT&CK Enterprise subset with ATT&CK version recorded, used by `get_mitre_technique` and MITRE-ID validation.

"New IP for user" is computed from bounded `security_events` history (no baseline table). Impossible travel fires only when fixture events carry `metadata.geo`. No geo-IP database is added.

### D-021 — Signal/alert model
- `detection_signals` = rule hits only (`rule_name` required).
- `alerts` = one per scored event at or above the alert threshold (defined and tested in Phase 04), holding `risk_score`, `anomaly_score`, `model_version`, `severity` and `reasons_json`, with unique `event_id`.
- `incident_alerts` links alerts to incidents, alongside `incident_events`.

### D-022 — AI service boundary and database roles
FastAPI is internal: only the Next.js server calls it, with a shared secret header (`AI_SERVICE_TOKEN`, added to `.env.example` in Phase 06). The AI service uses two PostgreSQL roles, created by migration in Phase 01:
- tools use a SELECT-only role;
- run/trace/evidence persistence uses a role limited to INSERT/UPDATE on `investigation_runs`, `investigation_trace` and `evidence`.

### D-023 — Local topology
- Docker Compose runs the infrastructure: PostgreSQL, Kafka (single-node KRaft, `apache/kafka` image) and Qdrant.
- During Phases 00–12, Next.js, the detection worker and FastAPI run on the host. Phase 13 adds them to Compose for clean-machine reproducibility.
- Ollama runs natively on the host (GPU access): `localhost:11434` from the host, `host.docker.internal:11434` from containers.
- Kafka advertises two listeners: `localhost:9092` for the host and `kafka:29092` for the Compose network.
- `.env.example` holds host values; Compose services override hostnames.

### D-024 — Toolchain
- Node.js current Active LTS with npm (no extra package manager).
- Python 3.12+ with `venv` + pip and pinned `requirements.txt` / `requirements-dev.txt` per service.
- Dev-only checks: ESLint + `tsc --noEmit`, ruff (lint) and mypy (type-check, enforcing "Python type hints").
- One cross-platform entrypoint, `python scripts/verify.py` (stdlib only), runs all checks; no `make`/bash dependency on Windows.
- No CI pipeline is planned. `scripts/verify.py` is the gate.

### D-025 — Startup refuses placeholder secrets
Services refuse to start when a required secret (e.g. `SESSION_SECRET`, `AI_SERVICE_TOKEN`) is missing or still equals its `.env.example` placeholder. Implemented when each secret is first used.

### D-026 — Phase dependency clarifications
- `mitre_techniques` and `ip_reputation` are seeded in Phase 01, so Phase 07's `get_mitre_technique` and `get_ip_reputation` are fully testable there.
- Phase 07 implements `search_security_knowledge` against a retriever interface tested with a fake. Phase 09 supplies the Qdrant implementation.
- Phase 06 defines the verdict Pydantic schema. Phase 08 runs end-to-end producing a schema-valid verdict. Phase 10 adds the hardened prompt, evidence-ID/MITRE-ID validation and the review path.

### D-027 — Harness workflow clarifications
- Phase status and gate-verdict vocabularies are defined once in `docs/18_HANDOFF_PROTOCOL.md`.
- Order: `/verify-phase` (gate) → `/handoff` (only after APPROVED) → commit → the next phase's receiver verifies.
- `progress/CURRENT_HANDOFF.md` is a pointer to the latest handoff file.
- Claude Code subagent files carry YAML frontmatter so they register.

### D-028 — PostgreSQL host port 5433 (Phase 00)
The Compose PostgreSQL publishes on `127.0.0.1:${POSTGRES_HOST_PORT}` with a default of `5433` in `.env.example`. The reference machine runs a native PostgreSQL 18 service on 5432, and native installs are common. Container-internal port stays 5432. Kafka's 9092 is fixed because it is the advertised host listener.

### D-029 — Service venvs use Python 3.12; dev tool and image pins (Phase 00)
Service venvs are created with Python 3.12 (D-024 allows 3.12+) for ML wheel availability (scikit-learn, torch via sentence-transformers). `scripts/verify.py` stays stdlib-only so it runs on any Python. Pinned in Phase 00:
- dev tools: ruff 0.16.10, mypy 2.4.0, pytest 9.1.1, TypeScript 6.0.3, ESLint 10.12.0, typescript-eslint 8.71.1, Vitest 5.0.3, @types/node 24.19.1;
- images: `postgres:17.6-alpine`, `apache/kafka:4.1.0`, `qdrant/qdrant:v1.15.0`.

### D-030 — Database-generated prefixed text IDs (Phase 01)
Primary keys are `text` with an entity prefix and 16 hex characters from `gen_random_uuid()`, generated by a column default (e.g. `inc_3f9a2b1c4d5e6f70`, `ev_…`). One rule serves TypeScript and Python without duplicated ID code. IDs are short enough for the LLM to cite exactly in `evidence_ids`; verdict validation (Phase 10) still checks exact matches. Prefixes: `an se sig alt inc run trc ev kd`. `ip_reputation` is keyed by `inet`, `mitre_techniques` by technique ID. The event timestamp column is `occurred_at` (docs/10 `*_at` naming); the API field stays `timestamp` and is mapped during normalization (Phase 03).

### D-031 — Roles are NOLOGIN; writer is append-only (Phase 01, refines D-022)
Migration `0001_roles.sql` creates `sentinelx_app`, `sentinelx_ai_tools` and `sentinelx_ai_writer` as NOLOGIN roles with explicit table grants. No role gets DELETE or TRUNCATE, and none can CREATE in `public`. The phase that first connects as a role (03 for app/detection, 06–07 for AI) adds LOGIN and a password from the environment, so no role password is committed. `sentinelx_ai_writer` gets INSERT/UPDATE on `investigation_runs` but INSERT only on `investigation_trace` and `evidence`: the audit trail is append-only. `sentinelx_ai_tools` cannot read `analysts` (password hashes) or investigation records. Tables added later must grant explicitly in their migration.

### D-032 — Phase 01 seeds reference data only (Phase 01)
`npm run db:seed` syncs `ip_reputation` and `mitre_techniques` from `fixtures/` (upsert + delete rows no longer in the fixture). No demo events, alerts or incidents are seeded: those must come from the Phase 03 deterministic generator through Kafka and detection, so there is a single path that exercises the real pipeline and no business logic is duplicated in a seed script. Phase 02 shows empty states until then. Fixture IPs must be RFC 1918 or RFC 5737 (enforced by the fixture validator).

### D-033 — Phase 01 database tooling (Phase 01)
- Pins: `drizzle-orm` 0.45.3, `pg` 8.23.1, `drizzle-kit` 0.31.11, `@types/pg` 8.23.1. 0.45.4 was released the same day and was skipped.
- `drizzle-kit generate` produces migrations; `npm run db:migrate` applies them with drizzle-orm's migrator (the same function the tests use).
- DB scripts run with Node 24's built-in TypeScript type stripping (`node src/db/cli.ts`), so no `tsx`/`ts-node` dependency; tsconfig enables `allowImportingTsExtensions` and `erasableSyntaxOnly`.
- `scripts/verify.py` detects schema drift by running `drizzle-kit generate` against a scratch copy of `drizzle/` and failing if a file is added.
- `npm audit` reports 4 moderate advisories in drizzle-kit's dev-only `@esbuild-kit` → esbuild ≤0.24.2 chain (esbuild dev-server issue; drizzle-kit never starts that server). Production dependencies audit clean. The only "fix" downgrades drizzle-kit to 0.18, so it is accepted until drizzle-kit drops `@esbuild-kit`.

## Open decisions (record before the owning phase starts)
| Topic | Owning phase |
|---|---|
| Auth/session implementation and password hashing algorithm | 02 |
| TypeScript Kafka client (kafkajs maintenance status vs Confluent's kafkajs-compatible client) | 03 |
| Isolation Forest feature list and alert threshold | 04 |
| Correlation window and grouping keys | 05 |
| Ollama model confirmation (`llama3.2:3b` default) and structured-output mode | 06 |
| Embedding model and vector dimension (default candidate `all-MiniLM-L6-v2`, 384-d, CPU torch) | 09 |
