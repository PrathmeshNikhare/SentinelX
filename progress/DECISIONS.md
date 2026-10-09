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

### D-034 — Analyst authentication and sessions (Phase 02; resolves the open Phase 02 decision)
- Passwords: Node's built-in `crypto.scrypt` (N=2^17, r=8, p=1, 16-byte salt, 32-byte key), stored as `scrypt$N$r$p$salt$hash` and compared with `timingSafeEqual`. OWASP-acceptable without a native dependency (argon2id would need prebuilt native binaries). Minimum length 12.
- Sessions are server-side in a new `analyst_sessions` table: `ses_` id, analyst_id, `token_hash` (SHA-256 of a 32-byte random token; the raw token exists only in the cookie), created_at, expires_at (8 h absolute), revoked_at. Logout sets `revoked_at` (the app role has no DELETE, D-031).
- Cookie `sx_session`: HttpOnly, SameSite=Lax, Path=/, Max-Age 8 h, Secure in production.
- Login and logout are Server Actions; Next.js rejects cross-origin Server Action posts (Origin vs Host), which covers CSRF for these forms. Unknown email and wrong password return the same message, and an unknown email still runs a scrypt comparison to keep timing similar.
- Boundary: `src/proxy.ts` (Next 16's replacement for `middleware.ts`) does an optimistic cookie-presence redirect to `/login`. Every console page and API route validates the session against PostgreSQL (`requireSession`); APIs return 401 JSON.
- No signed cookies, so `SESSION_SECRET` is unused and removed from `.env.example`. D-025 then applies to `AI_SERVICE_TOKEN`.
- Accounts are created with `npm run analyst:create -- <email> "<name>"`, password from the `ANALYST_PASSWORD` environment variable, using the owner connection. No default account is seeded.
- Login rate limiting and lockout are deferred to Phase 12 (auth hardening).

### D-035 — The web app connects as `sentinelx_app` (Phase 02)
The Next.js server uses `APP_DATABASE_URL` (role `sentinelx_app`), never the owner `DATABASE_URL`. `npm run db:roles` (owner) enables LOGIN for `sentinelx_app` and sets its password from `APP_DATABASE_URL`, so no role password lives in migrations (D-031). The AI roles stay NOLOGIN until Phases 06–07. Migration `0002` adds `analyst_sessions` with grants: `sentinelx_app` SELECT/INSERT/UPDATE; AI roles none.

### D-036 — Web UI structure (Phase 02)
- Tailwind CSS v4 + shadcn/ui components copied into `src/components/ui`; system font stack (no build-time font download).
- Server Components read data through typed query functions in `src/server/queries/`, guarded by the `server-only` package.
- Each data view handles loading (`loading.tsx`), empty (explicit empty state), not-found, error (`error.tsx`) and degraded states. A query that fails because PostgreSQL is unreachable renders a "data unavailable" panel instead of crashing the page.
- Only real counts are shown: no placeholder metrics or charts until real data exists (Phase 03+).
- API routes: `GET /api/incidents` and `GET /api/incidents/:id` are real; `POST /api/events` (Phase 03), `POST /api/incidents/:id/investigate` and `GET /api/investigations/:id` (Phases 06–08) return 501 with the owning phase.

### D-037 — Phase 02 tests: Playwright against a production build (Phase 02)
`npm run test:e2e` builds once and starts two `next start` servers: a healthy one on port 3100 using a throwaway `sentinelx_e2e` database, and a degraded one on port 3101 pointed at an unreachable database. The suite covers:
- auth redirect, failed and successful login, logout with server-side revocation;
- empty states and not-found;
- API 401/501;
- degraded rendering.

Chromium only. Pure logic (password hashing, session tokens, ID validation) has Vitest unit tests; session storage has DB integration tests.

### D-038 — Phase 02 dependencies and fixes (Phase 02)
- Pins: `next` 16.3.8, `react`/`react-dom` 19.3.0, `tailwindcss`/`@tailwindcss/postcss` 4.3.3, `eslint-config-next` 16.3.8, `@playwright/test` 1.63.0, `server-only` 0.0.1, `radix-ui` 1.6.6, `lucide-react` 1.47.0, `class-variance-authority` 0.7.1, `cn` 0.4.0. All exact.
- Security exception to the two-week age rule: `npm audit` flagged high-severity Next.js advisories for 16.0.0–16.3.7 (image-optimizer SSRF, cache poisoning, information disclosure). Upgraded from 16.3.6 to the 16.3.8 patch (released 2026-09-30).
- The shadcn 4 CLI generates components that import `cn` from the npm package `cn`, published by shadcn himself from the `shadcn-ui/cn` repo. Checked: no install scripts, no dependencies. Kept and pinned.
- The CLI also added `shadcn` (published the day before) and `tw-animate-css` only for CSS imports our five components don't use; both were removed (−225 packages). Add components later with `npx shadcn@4.21.0 add <name>`.
- `eslint-plugin-react` (via `eslint-config-next`) calls `context.getFilename()`, which ESLint 10 removed. Setting `settings.react.version` avoids its version detection. Probes confirmed the Next.js and hooks rules fire. Lint runs with `--max-warnings 0`.
- `eslint-plugin-import` (via `eslint-config-next`) declares ESLint ≤9 as its peer, so npm prints an ERESOLVE override warning on install. It is harmless: its rules load under ESLint 10.
- `npm audit --omit=dev`: 0 vulnerabilities. Dev-only advisories remain in drizzle-kit (esbuild ≤0.24.2, D-033) and in `@next/eslint-plugin-next`'s `fast-glob` → `braces` (no patched `braces` exists; it only expands our own lint globs).
- Next.js reads the repo-root `.env` through `next.config.ts`. App code must not import `src/db/env.ts`: Turbopack treats `new URL(".env", import.meta.url)` as an asset and would bundle the file (the build failed on it).
- Error logging never includes query parameters: Drizzle errors carry bound values (emails, token hashes, password hashes), so `describeError` keeps only the SQL text and driver code. The session check returns `ok | anonymous | unavailable` instead of throwing, because Next renders pages in parallel with layouts.

### D-039 — Commit Next.js-generated `apps/web/AGENTS.md` and `CLAUDE.md` (Phase 02)
`next dev` (Next 16, `node_modules/next/dist/server/lib/generate-agent-files.js`) writes `apps/web/AGENTS.md` (a managed block telling coding agents to read the bundled Next.js 16 docs in `node_modules/next/dist/docs/` before writing code) and `apps/web/CLAUDE.md` (`@AGENTS.md`) when it detects an AI coding agent. The content was reviewed: it is accurate (Next 16 renamed `middleware.ts` to `proxy.ts`, etc.) and does not conflict with the root `CLAUDE.md`. The files are committed so this agent instruction is visible and reviewed, and so `next dev` does not leave the tree dirty. Do not hand-edit the managed block; `next dev` rewrites it.

### D-040 — Kafka client: `@confluentinc/kafka-javascript` (Phase 03; resolves the open Phase 03 decision)
- `kafkajs` has had no release since 2.2.4 (2023-02-27). Confluent's official librdkafka binding exposes a KafkaJS-compatible API and is actively released; 1.10.1 (2026-09-10) is pinned.
- Its install script (`node-pre-gyp install --fallback-to-build`) downloads a prebuilt native binary from Confluent's GitHub releases; on Windows it installed without a compiler.
- It is listed in `serverExternalPackages`. Client settings:
  - `broker.address.family=v4`: librdkafka otherwise tries `::1` first while Docker publishes on 127.0.0.1, costing about 2 s and an error per connect;
  - client logger `NOTHING`: failures surface as rejected promises, logged once by our code.
- Verified by a produce→consume round trip against the Compose broker.

### D-041 — `POST /api/events` authentication (Phase 03; resolves the Phase 02 handoff question)
- The endpoint accepts either a valid analyst session or `Authorization: Bearer <INGEST_API_TOKEN>`. The token is for non-browser producers, starting with the demo generator, so every event, demo included, passes the same validation path.
- Comparison: SHA-256 of both values plus `timingSafeEqual`. Token auth is disabled when `INGEST_API_TOKEN` is empty, and refused (logged as misconfiguration) when the token is shorter than 32 characters (D-025).
- The token path never touches PostgreSQL, so ingestion keeps working while the database is down (D-014).

### D-042 — Event contracts: zod source, generated JSON Schema (Phase 03; refines D-011)
- The TypeScript zod schemas in `apps/web/src/contracts/` are the source of truth.
- `npm run contracts:generate` writes language-neutral JSON Schema (draft 2020-12) to `contracts/v1/security-event.schema.json` (API body) and `contracts/v1/normalized-event.schema.json` (Kafka message).
- A unit test fails if the committed files drift from the zod schemas. Examples in `contracts/v1/examples/` are validated in tests.
- Python consumers (Phase 04) validate against the generated JSON Schema or a Pydantic model with a contract test on the same examples.
- zod 4.6.5 is pinned (boundary validation is required by CLAUDE.md; it also gives typed parsing and field-level error paths for 400 responses).

### D-043 — Event semantics, normalization and the Kafka message (Phase 03)
API body: a strict object (unknown fields rejected) with:
- `event_id`: `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`;
- `timestamp`: ISO 8601 with offset;
- `user_id`: `[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}`;
- `source_ip`: IPv4 or IPv6;
- `event_type`: `authentication | process | file_access | privilege_change | network`;
- `action`: `[A-Za-z0-9_.-]{1,64}`;
- `resource`: 1–512 characters, no control characters;
- `status`: `success | failed`;
- optional `metadata`: JSON object, keys 1–64 characters, no `constructor`/`prototype` keys, serialized at most 4 KiB. A `__proto__` key anywhere in the body is rejected by the JSON reviver in the route (zod 4 would silently drop it).

Request limits: `application/json` only (else 415); body at most 16 KiB (else 413).

Normalization (pure, `now` injected):
- `timestamp` → `occurred_at` in UTC ISO (`…Z`); more than 5 minutes in the future is rejected;
- `user_id` and `action` are lowercased (one identity per user for correlation);
- IPv6 is canonicalized; IPv4-mapped IPv6 (`::ffff:a.b.c.d`) becomes IPv4;
- `resource` is trimmed;
- `schema_version: "v1"` and `ingested_at` are added.

Kafka message on topic `security-events`: key `user_id` (D-014), JSON value = the normalized event, headers `schema-version: v1` and `content-type: application/json`. The API answers `202 {event_id, status: "accepted"}`, or `503` when Kafka does not acknowledge within 8 s. Deduplication stays in the detection worker (D-014).

### D-044 — Deterministic demo generator (Phase 03)
- Scenarios A/B/C (docs/12) live in `fixtures/scenarios/scenario-{a,b,c}.json` as events with `offset_seconds`.
- `npm run demo:send -- <A|B|C> [--base <ISO>] [--url <base-url>]` expands a scenario and posts each event to `POST /api/events` with `INGEST_API_TOKEN`.
- The default base is now minus the scenario's largest offset, so the last event lands "now" (inside the 5-minute skew window) and the overview's 24 h counts include it.
- `event_id = demo-<scenario>-<base as yyyymmddThhmmssZ>-<nn>`: the same scenario and base always yield the same events, and re-sending yields the same IDs (the worker dedupes them). Fixture IPs follow D-032 (RFC 1918/5737 only).

### D-045 — Test traffic never uses the production topic (Phase 03)
- The producer topic comes from `KAFKA_EVENTS_TOPIC` (default `security-events`).
- The Kafka integration tests publish to `security-events-test` and the E2E servers to `security-events-e2e`; both topics are created on demand by `ensureTopic`.
- Only real ingestion (including `npm run demo:send`) reaches `security-events`, so the Phase 04 worker never consumes test noise. Kafka has no volume (D-023): recreating the broker container empties every topic.

### D-046 — Phase 04 scope: the worker persists events and signals; alerts and incidents are Phase 05 (Phase 04)
The detection worker (`python -m sentinelx_detection.worker`):
1. consumes `security-events`;
2. validates each message against `contracts/v1/normalized-event.schema.json`;
3. upserts `security_events` (replay-safe: an existing `external_event_id` returns its row id);
4. computes rules, features, anomaly score and risk;
5. inserts `detection_signals` with `ON CONFLICT (event_id, rule_name) DO NOTHING`.

Alert persistence (risk ≥ threshold, D-050) and correlation into incidents are Phase 05 scope (docs/07). Processing uses event time only, never wall-clock time, so re-consuming the topic reproduces the same results. Phase 05 adds alerts by replaying from the beginning (new consumer group or offset reset).

### D-047 — Python detection stack (Phase 04; resolves the consumer/DB questions in the Phase 03 handoff)
- Pins: `confluent-kafka` 2.15.1 (librdkafka, mirroring D-040; `broker.address.family=v4`), `psycopg[binary]` 3.3.6 (D-010), `numpy` 2.5.3, `scikit-learn` 1.9.1, and `jsonschema` 4.26.0, which validates against the generated contracts so Python never re-declares the event shape (D-042). Transitive dependencies are frozen in `requirements.txt`.
- `pandas` is not added: nothing in Phase 04 needs it. The stack permits it if a later phase does.
- Delivery: `enable.auto.commit=false`; the offset is committed after an event is fully processed (at-least-once, with idempotent writes).
  - A malformed or contract-invalid message is logged (no payload) and committed, i.e. skipped: a poison message must not block the partition.
  - A database or broker error is not committed: the worker backs off and retries the same message, so no event is lost.
- The worker connects as `sentinelx_app` through `APP_DATABASE_URL` (D-035 already assigns that role to web + detection). Consumer group: `sentinelx-detection`.

### D-048 — Deterministic detection rules (Phase 04)
All rules are evaluated at the event's `occurred_at` against PostgreSQL history strictly before it. Rule severity derives from the score using the risk bands (D-050). Login = `event_type=authentication, action=login`.

| Rule | Fires when | Score |
|---|---|---|
| `brute_force_attempts` | failed login and ≥5 failed logins for the user in the last 10 min (including this one) | 60 |
| `login_after_failures` | successful login after ≥3 failed logins for the user in the previous 15 min | 75 |
| `new_ip_login` | successful login from an IP with no successful login by the user in the previous 30 days (failed attempts do not make an IP known), unless the IP is `known_good` | 35 |
| `risky_ip_login` | successful login from a `suspicious` / `malicious` IP (`ip_reputation`) | 50 / 80 |
| `suspicious_powershell` | `powershell.exe`/`pwsh.exe` process whose command line has encoded-command, hidden-window, `iex`/`invoke-expression`, `downloadstring`/`net.webclient` or `frombase64string` indicators | 70 (one indicator), 85 (two or more) |
| `sensitive_file_access` | file access with `metadata.sensitivity` in confidential/restricted/secret, or a path naming payroll/salary/finance/hr/credential/password/secret | 50 |
| `privilege_escalation` | successful `privilege_change` event | 70 |
| `impossible_travel` | successful login whose `metadata.geo.country` differs from a successful login by the user in the previous 2 h (fixtures without `geo` never fire it, D-020) | 75 |
| `post_compromise_chain` | process or file-access event within 30 min after a `login_after_failures` or malicious `risky_ip_login` signal for the user | 85 |

### D-049 — Features and Isolation Forest (Phase 04; resolves the open Phase 04 feature decision)
Feature vector, in a fixed order (event time):
1. hour-of-day sine and cosine (UTC);
2. is_weekend;
3. is_failure;
4. one-hot `event_type` (5);
5. failed logins for the user in 15 min;
6. user events in 1 h;
7. distinct user IPs in 24 h (counts include the current event, capped at 50);
8. is_new_ip_for_user (no successful login from it in 30 days);
9. IP reputation score / 100 (0.25 when the IP is not in `ip_reputation`);
10. is_sensitive_resource;
11. is_script_process.

Training: `python -m sentinelx_detection.train` generates a seeded synthetic baseline (40 users, 21 days of business-hour sessions from corporate IPs, normal file and admin activity), replays it through the same feature code, and fits `IsolationForest(n_estimators=200, max_samples=256, contamination="auto", random_state=42)`.

Output: `services/detection/models/iforest-v1.joblib` plus a JSON metadata file. The model version is content-addressed: a SHA-256 over the training matrix, feature list, parameters and sklearn version.

Anomaly score = `1 / (1 + exp(12 · decision_function))`, in [0, 1] with 0.5 at sklearn's outlier boundary.

The artifact is not committed: training is deterministic, and the worker fails fast with instructions if the file is missing. `joblib.load` unpickles, so only locally trained artifacts are ever loaded, never downloaded ones.

### D-050 — Deterministic risk engine and alert threshold (Phase 04; resolves the open Phase 04 threshold decision)
Inputs:
- R = the highest rule score on the event;
- A = 100 × anomaly score;
- P = IP reputation score (25 when unknown);
- C = min(100, 25 × distinct rule names fired for the user in the last 60 min, including this event): the correlation/context term.

`risk = clamp(round(0.45·R + 0.25·A + 0.15·P + 0.15·C), 0, 100)`. Levels: LOW 0–29, MEDIUM 30–59, HIGH 60–79, CRITICAL 80–100 (docs/01).

Alert threshold: risk ≥ 40 (Phase 05 persists alerts). The scenario traces behind the numbers:
- B (`known_good` IP, no rules) is capped at 0.25·A ≤ 25: never alerts.
- C's first login (`risky_ip_login` 50 + `new_ip_login`, P = 55, C = 50) is ≥ 38.25 + 0.25·A, so it alerts as MEDIUM, enabling the docs/12 "cautious verdict" investigation.
- A reaches ≈ 85–90 at the PowerShell/file events (R = 85, C = 100, P = 90), matching docs/03's "risk ~90".

The LLM never computes or overrides this score (D-004).

### D-051 — psycopg prefers IPv4 for `localhost` and is time-bounded (Phase 04)
On Windows, psycopg tried `localhost` as `::1` first and stalled until its timeout before falling back to IPv4: 90 s versus 0.07 s via `127.0.0.1`, because Docker publishes PostgreSQL on 127.0.0.1 only. This made the worker look hung. Node's `pg` is unaffected.
- `sentinelx_detection.repository.connect()` passes `hostaddr=127.0.0.1` when the URL host is `localhost`, the client-side equivalent of `broker.address.family=v4` for Kafka (D-040).
- It always sets `connect_timeout=10` (psycopg's default is unbounded), so a misconfigured host fails fast instead of hanging.
- No `.env` change is needed; the protected `.env` is not touched.

### D-052 — Alert persistence (Phase 05)
The worker writes an `alerts` row when `risk ≥ 40` (D-050), in the same per-event transaction as the event and its signals, with `ON CONFLICT (event_id) DO NOTHING` (replay-safe).
- `severity` = the event's risk level.
- `reasons_json` makes the score explainable: `{"signals": [{rule, score, reason}], "components": {"rule", "anomaly", "reputation", "context"}, "formula": "0.45R + 0.25A + 0.15P + 0.15C"}`.
- `risk_score`, `anomaly_score` and `model_version` come from the detection result.

### D-053 — Correlation: per monitored user, 60-minute event-time window (Phase 05; resolves the open Phase 05 decision)
Correlation runs in the detection worker after detection, using event time only, so replay is deterministic. The grouping key is `user_id`. A user's *active* incident is their most recent non-`resolved` incident. Each event is checked against it:
- **Already linked** to an incident (replay): no change.
- **Within `[started_at − 60 min, last activity + 60 min]`** of the active incident, where last activity is the latest linked event's `occurred_at`: linked to the incident, together with its alert if it has one. Non-alerting events are linked too, so the incident timeline is complete.
- **Otherwise, an alerting event** creates a new incident. The user's not-yet-linked events from the previous 60 minutes are linked as context; for example, scenario A's four failed logins before the brute-force alert.
- **Otherwise**: nothing.

Incident fields are recomputed from the linked rows after each change (idempotent):
- `risk_score` = highest alert risk, `severity` = its level;
- `primary_ip` = the IP of the highest-risk alert;
- `started_at` = the earliest linked event;
- `title` = a deterministic label from the highest-priority rule among the incident's signals (compromise chain or login-after-failures → "Possible account compromise", privilege escalation, PowerShell, impossible travel, brute force, risky IP, new IP, sensitive file, else "Anomalous activity") plus the user.

Incidents never merge or split, and a `resolved` incident is never reopened by detection: new activity opens a new incident. Deferred: IP-keyed correlation across users (password spraying), which would create one incident per targeted user.

### D-054 — Incident lifecycle (Phase 05)
States: `open`, `investigating`, `resolved`. Allowed transitions:

| From | To |
|---|---|
| `open` | `investigating`, `resolved` |
| `investigating` | `open`, `resolved` |
| `resolved` | `open` (manual reopen only) |

Transitions are analyst actions in the web app: `PATCH /api/incidents/:id {"status"}` and buttons on the incident page. They apply as one conditional `UPDATE … WHERE status IN (allowed sources)`, so concurrent changes cannot skip the rules. An invalid transition returns 409. Each change is logged as `incident.status_changed` (analyst id, from, to); a persistent audit table is Phase 12. Detection only reads status (non-`resolved` = active) and never changes it.

### D-055 — Backfilling the dev database (Phase 05)
Events processed before Phase 05 got no alerts. The worker is replayed once with a fresh consumer group (`--group backfill-phase05`), which is deterministic and idempotent (D-046), to create their alerts and incidents. The long-running worker keeps group `sentinelx-detection`.

### D-056 — Ollama model and structured output (Phase 06; resolves the open Phase 06 decision)
- The default model stays `llama3.2:3b` (`.env.example`; installed on the reference machine, 2.0 GB Q4_K_M). The adapter is model-agnostic through `OLLAMA_MODEL` (for example `gemma4:e2b`).
- Structured output uses Ollama's `format` parameter set to the Pydantic model's JSON Schema, with `temperature=0` and `seed=42`. This is near-deterministic, not guaranteed: with the full verdict schema, two identical calls differed in one MITRE ID (`T1210` vs `T1210.001`). Nothing downstream may rely on identical LLM output; the deterministic parts of the system stay in detection.
- The response is still re-validated with Pydantic: constrained decoding is never trusted alone (CLAUDE.md).
- `OLLAMA_TIMEOUT_SECONDS` defaults to 120: a measured cold call took 40.5 s (11 s model load), a warm one 7.2 s.
- The probe also showed the model inventing MITRE IDs (`T1003`, `T1210`) for brute force plus PowerShell evidence. Schema validation cannot catch that; evidence-ID and MITRE-ID existence checks are Phase 10.

### D-057 — AI service structure (Phase 06)
- Pins: `fastapi` 0.141.1, `uvicorn` 0.53.0, `httpx` 0.28.1, `pydantic` 2.13.5 (transitives frozen; OSV reported no advisories).
- The Ollama adapter is a thin `httpx` client behind an `LlmClient` protocol: explicit timeouts, no hidden retries, testable with `httpx.MockTransport`. It does not use `langchain-ollama`; LangChain and LangGraph arrive with the tools and graph (Phases 07–08).
- The service binds `127.0.0.1:8000` (internal, D-022). Endpoints:
  - `GET /health`: public liveness, no details;
  - `GET /v1/ready`: authenticated; reports whether Ollama is reachable and the model present;
  - `POST /v1/investigations`: authenticated; validates the request contract and returns 501 until Phase 08.
- Errors use the web app's JSON shape `{"error": {"code", "message"}}`.

### D-058 — Internal service authentication (Phase 06)
- Every route except `/health` requires `Authorization: Bearer <AI_SERVICE_TOKEN>`, compared in constant time (SHA-256 digests plus `hmac.compare_digest`).
- The service refuses to start when the token is missing, shorter than 32 characters or a known placeholder (D-025).
- OpenAPI docs (`/docs`, `/redoc`, `/openapi.json`) are disabled, so nothing describes the API to unauthenticated callers.

### D-059 — AI-owned contracts: Pydantic source, generated JSON Schema (Phase 06; refines D-042)
Each contract's source of truth lives in the service that owns it.
- The verdict, investigation-request and investigation-accepted contracts are Pydantic models in `services/ai`.
- `python -m sentinelx_ai.contracts` writes `contracts/v1/{verdict,investigation-request,investigation-accepted}.schema.json`; a pytest drift test keeps them in sync, and examples live in `contracts/v1/examples/`.

Verdict rules (CLAUDE.md shape, extra fields forbidden):
- `verdict` 3–120 characters; `confidence` 0–1; `severity` LOW/MEDIUM/HIGH/CRITICAL; `summary` 1–2000 characters;
- `evidence_ids`: 1–20 unique `ev_` IDs (D-030); `mitre_techniques`: 0–10 unique `T####(.###)`;
- `recommendations`: 1–10 items of 3–300 characters each.

Whether the cited IDs actually exist is checked in Phase 10.

### D-060 — Agent tools on LangChain `StructuredTool` (Phase 07)
- Pins: `langchain-core` 1.6.7 and `psycopg[binary]` 3.3.6 (as detection, D-047). 1.6.8 and 1.6.9 were released the day before Phase 07 and were skipped (as in D-033). LangGraph 1.2.x (Phase 08) requires `langchain-core>=1.4.7`. OSV reported no advisories for the 52 frozen packages.
- Why LangChain here: the stack names LangChain tools for the agent. Each tool is a `StructuredTool` whose `args_schema` is a Pydantic model, so Phase 08's graph can validate an LLM's proposed action against the same schema (D-017) and render the tool list for the prompt. The Ollama adapter in `llm.py` stays the only LLM path; `langchain-ollama` is not added.
- `langsmith` arrives as a `langchain-core` dependency and uploads traces to a cloud service when `LANGSMITH_TRACING`/`LANGCHAIN_TRACING_V2` (or the older names) is `true`. That would send investigation data off the machine, so the service refuses to start when any of them is set (D-025 style).

### D-061 — The tools connect only as `sentinelx_ai_tools` (Phase 07; refines D-031)
- `npm run db:roles` (owner) now enables LOGIN for both `sentinelx_app` and `sentinelx_ai_tools`, each with the password from its URL (`APP_DATABASE_URL`, `AI_TOOLS_DATABASE_URL`). `sentinelx_ai_writer` stays NOLOGIN until Phase 08.
- `connect_tools()` checks `current_user` after connecting and refuses any other role. Even a misconfigured URL with owner credentials cannot run the tools.
- Sessions set `default_transaction_read_only=on`, `statement_timeout=2000ms` and `TimeZone=UTC`, use `connect_timeout=10` and IPv4 for `localhost` (D-051), and run in autocommit with one short-lived connection per call. The grants are the enforcement; the read-only default is defense in depth. Tests prove the grants in an explicit `READ WRITE` transaction.

### D-062 — Tool bounds (Phase 07)
| Tool | Input bounds | Output |
|---|---|---|
| `get_user_history` | `user_id` (event-contract pattern), aware `start_time < end_time`, window ≤ 7 days, `limit` 1–50 (default 20) | events newest first, `truncated` |
| `get_related_logs` | as above, but `user_id` and/or `source_ip` (at least one, so it is never an unscoped scan); `event_types` 1–5 unique contract values | same |
| `get_ip_reputation` | `ip` (IPv4/IPv6, no CIDR) | `known=false`, `reputation=unknown` for unseeded addresses |
| `get_mitre_technique` | `T####(.###)` | `found=false` for IDs outside the curated set |
| `search_security_knowledge` | `query` 3–500 characters, no control characters; `top_k` 1–10 (default 5) | hits with `kd_` document IDs, `truncated` |
- Inputs forbid unknown fields. Every result is at most 32 KiB serialized: event and hit lists drop trailing items and set `truncated`; any other oversized result is a `ToolError` (`oversized`).
- Event rows carry `event_id` (the `se_` row ID) so Phase 08 evidence can reference persisted rows.
- Failures are `ToolError(tool, code)` with code `timeout`, `unavailable` or `oversized`. The message never includes SQL, parameters or row data.
- Queries are three module constants, each a single `SELECT` with named parameters. Optional filters use `%(x)s IS NULL OR …`, not string building. A unit test parses the module and fails on imports outside the allowed set (no `subprocess`/`os`/`socket`/HTTP clients), on calls to `eval`/`exec`/`open`, and on any `execute()` whose query is not a constant.

### D-063 — Knowledge retriever interface (Phase 07; implements D-026)
`KnowledgeRetriever.search(query, top_k, timeout_seconds) -> Sequence[KnowledgeHit]`. Implementations honor the 5 s timeout and raise `TimeoutError` or `ConnectionError`, which the tool maps to `ToolError`. `KnowledgeHit` carries `document_id` (`kd_` + 16 hex, i.e. `knowledge_documents.id`, D-018), `source`, `title` (≤ 300), `snippet` (≤ 1500) and a finite `score`. Phase 07 tests use a fake. Phase 09 supplies the Qdrant implementation and decides whether hits must be checked against `knowledge_documents`.

### D-064 — Investigation flow and graph (Phase 08; implements D-015, D-017)
- Pin: `langgraph` 1.2.14 with `langgraph-checkpoint` 4.2.0, `langgraph-prebuilt` 1.1.0, `langgraph-sdk` 0.4.6 and `ormsgpack` 1.12.2. `langgraph-sdk` requires `websockets<17`, so `websockets` moved from 17.2 to 16.1.1. No checkpointer is used: runs are not resumed, and state lives in the trace.
- The AI service owns run creation (the web role cannot write `investigation_runs`, D-031). `POST /v1/investigations` takes a per-incident advisory lock and inserts a `queued` run unless one is already queued or running, then returns `202` with `investigation_run_id` and schedules the graph as a FastAPI background task. Otherwise: `404` for an unknown incident, `409 investigation_in_progress`, or `503` when the database or role is unavailable.
- Graph (docs/05): `load_incident → analyze_evidence → choose_next_action → execute_tool → store_evidence → analyze_evidence … → build_verdict → validate_verdict`. At most 8 tool executions (`MAX_STEPS`). The LangGraph recursion limit of 42 is a safety net above that.
- `choose_next_action`: the LLM proposes `{action, arguments}` (an action enum including `finish`; no free-text rationale, docs/15). The proposal is rejected and replaced by the next unexecuted fallback-plan action when it fails `TOOL_INPUTS[tool]` validation, names a tool that is not offered, or repeats an executed action. An exhausted plan ends the loop. After `LlmUnavailable` the run stops asking the LLM for actions; `LlmInvalidOutput` falls back for that step only.
- Trace rows (append-only, contiguous `step_index`): `load_incident` (counts plus the fallback plan), `choose_action` (origin, the proposal (cut to its action name when over 2,000 characters), the selected action, the reason), `tool_call` (origin, canonical arguments, ok/error, claims, evidence IDs, retrieval refs), `build_verdict`, `validate_verdict`.
- Live on `llama3.2:3b` (reference machine), for scenario A and the dev demo incident: 58–61 s per run. The model's first four proposals were valid; it then repeated actions and the fallback plan filled the remaining budget.

### D-065 — Writer role and run lifecycle (Phase 08; refines D-031)
- `npm run db:roles` also enables LOGIN for `sentinelx_ai_writer` from `AI_WRITER_DATABASE_URL`. All three non-owner roles can now log in.
- `Store` connects per operation with a 5 s statement timeout, `TimeZone=UTC` and IPv4 for `localhost`. It checks `current_user = sentinelx_ai_writer` and refuses any other role. Trace and evidence are INSERT-only (grants).
- `python -m sentinelx_ai` refuses to start unless both database URLs are set, the tools URL connects as the tools role and the writer URL as the writer role. At startup it marks runs left `queued`/`running` by a previous process as `failed` with `requires_review=true` (`ponytail:` single instance, D-023).
- A crash inside a run (database error, missing incident) finishes it as `failed` with `investigation failed (<ExceptionType>)`. No exception text is stored or logged.

### D-066 — Investigation evidence and the fallback plan (Phase 08; implements D-018)
- `load_incident` stores the incident's newest 20 linked events (with their rule names) and its 10 highest-risk alerts as `event`/`alert` evidence. Each tool result becomes evidence: one row per call, or one row per hit for knowledge search. Source IDs: user ID (`user_history`), the filter scope (`related_logs`), the IP, the technique ID, the `kd_` document ID.
- Claims are written by code (`evidence.py`), never by the model. Log-derived fields are clipped to 120 characters with whitespace collapsed, so injected newlines cannot forge extra `[ev_…]` prompt lines. Prompts show `[ev_id] (source_type) claim` only; `data_json` keeps the bounded source data for audit and the UI.
- Fallback plan, in order: user history (24 h before the first event to 1 min after the last, at most 7 days), reputation of up to 3 incident IPs (primary first), related logs for the primary IP, and up to 4 candidate ATT&CK techniques from the incident's rule hits (`RULE_TECHNIQUES`, e.g. `brute_force_attempts → T1110`, `suspicious_powershell → T1059.001`). The map is a lookup hint, not a verdict, and duplicates no detection logic.

### D-067 — No knowledge search until a retriever exists (Phase 08; refines D-063)
`build_tools(db, None)` omits `search_security_knowledge`, so the agent is never offered a tool that always returns nothing. Phase 09 passes the Qdrant retriever and the tool appears in `available_tools` with no graph change.

### D-068 — Verdict handling in Phase 08 (implements D-019 partially)
- Live finding: Ollama's `format` does not enforce numeric bounds. `llama3.2:3b` sometimes returned `confidence` above 1 (a percentage) twice in a row, so the run went to review. Two fixes: the verdict prompt states the 0.0–1.0 range, and the retry names the rejected fields (`describe_validation_error` types only, never the output), because the identical prompt at temperature 0 repeats the mistake. After the change, 3 consecutive live runs completed without review. The Phase 06 live adapter test's prompt also states the range.
- `build_verdict` makes up to 2 attempts (retry once on invalid output). Every attempt is kept in `raw_output_json.attempts` (`valid`, `error`, bounded `raw`, or the validated `output`). `verdict_json` holds only a schema-valid verdict.
- No valid attempt: `completed`, `requires_review=true`, `validation_errors_json` lists the errors. Ollama unavailable: `failed`, `requires_review=true`, `error_message`, evidence and trace kept.
- `validate_verdict` records `checks: ["schema"]` and `deferred_to_phase_10: ["evidence_ids", "mitre_techniques", "severity_disagreement"]`. Until Phase 10, a schema-valid verdict may cite IDs that do not exist. In both live runs every cited ID existed, but the dev-incident summary miscounted the failed logins (4 vs 5): grounding is Phase 10 work.

### D-069 — Web side of investigations (Phase 08)
- `POST /api/incidents/:id/investigate` checks the incident in the web database first (404 without calling the AI service), then calls `POST /v1/investigations` with the service token. The call uses a 5 s timeout and `redirect: "error"`, and the 202 response is validated against the `investigation-accepted` contract (zod in `src/contracts/investigation.ts`). Responses: 202 `{investigation_run_id}`, 404, 409, or 503 when the service is unreachable, misconfigured (missing token or one under 32 characters) or violates the contract.
- `GET /api/investigations/:id` returns the run (status, `requiresReview`, verdict, validation errors, model, prompt version, timestamps), the trace by step and the evidence, as `sentinelx_app`. `raw_output_json` is not served.
- The incident page gets an Investigate button (server action, outcome shown as a status line) and the latest run's status. The full trace, verdict and evidence UI is Phase 11.
- E2E servers point `AI_SERVICE_URL` at a closed port: the unavailable path is deterministic, and a run inserted as the owner exercises the read path. The live graph is covered by `services/ai/tests/integration/test_investigation_live.py`.
- The `notImplemented` helper is removed: no placeholder endpoints remain.

## Open decisions (record before the owning phase starts)
| Topic | Owning phase |
|---|---|
| ~~Auth/session implementation and password hashing algorithm~~ — resolved by D-034 | 02 |
| ~~TypeScript Kafka client~~ — resolved by D-040 | 03 |
| ~~Isolation Forest feature list and alert threshold~~ — resolved by D-049, D-050 | 04 |
| ~~Correlation window and grouping keys~~ — resolved by D-053 | 05 |
| ~~Ollama model confirmation and structured-output mode~~ — resolved by D-056 | 06 |
| Embedding model and vector dimension (default candidate `all-MiniLM-L6-v2`, 384-d, CPU torch) | 09 |
