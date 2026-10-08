# Phase 03 — Event Ingestion — Handoff

PHASE: 03
STATUS: READY_FOR_NEXT_PHASE
GATE: `/verify-phase` APPROVED (2026-10-08)
BASE COMMIT: `b428834` (Phase 02). Phase 03 is the commit that adds this file.
PREVIOUS PHASE: 02 accepted as COMPLETE at the start of this phase (verify.py 22/22 incl. unit/DB/E2E reproduced).

## Objective
Event schema, normalization, API ingestion, Kafka producer, controlled demo generator. Exit: event travels into Kafka; validation tests pass.

## Completed work
- Contracts (D-042): zod source `apps/web/src/contracts/security-event.ts` → generated `contracts/v1/security-event.schema.json` (API body) and `normalized-event.schema.json` (Kafka value), plus an example pair in `contracts/v1/examples/`. A drift test keeps the files in sync (`npm run contracts:generate`).
- Normalization (D-043, pure): `timestamp` → UTC `occurred_at`, future skew > 5 min rejected, lowercase `user_id`/`action`, canonical IPv6, IPv4-mapped → IPv4, trimmed `resource`, `schema_version`/`ingested_at`.
- `POST /api/events` (D-041, D-043): Bearer `INGEST_API_TOKEN` (constant-time, no DB) or analyst session. Checks: JSON content type (415), streamed 16 KiB cap (413), JSON reviver rejecting `__proto__` anywhere, contract validation with field paths (400), clock skew. Then Kafka publish (acks=all, idempotent producer, 8 s bound) → 202, or 503. Log line `ingest.accepted` carries id/type/auth only.
- Kafka (D-040, D-045): `@confluentinc/kafka-javascript` 1.10.1 (prebuilt native binary, `serverExternalPackages`), IPv4 only, client logger silenced. Topic from `KAFKA_EVENTS_TOPIC` (default `security-events`). Tests use `security-events-test` / `security-events-e2e` via `ensureTopic`.
- Demo generator (D-044): `fixtures/scenarios/scenario-{a,b,c}.json` (synthetic IPs enforced) + `npm run demo:send -- <A|B|C> [--base] [--url]`, deterministic event IDs, default base ends at "now".
- `isSyntheticIp` exported from `src/db/reference-data.ts` and reused by scenario validation.
- `scripts/verify.py`: new `web: kafka integration` check (23 checks); the Phase 00 Kafka limitation note is retired.
- The Kafka broker was recreated once during verification to purge two non-contract smoke-test messages from `security-events`. The topic now holds exactly scenarios A, B and C (17 events) sent through the real API.
- `.env.example`: `INGEST_API_TOKEN=` (empty = disabled). The local `.env` got a generated 43-character token (value never printed).

## Files changed
Added: `apps/web/src/contracts/{security-event,generate}.ts` + `contracts.test.ts`, `apps/web/src/ingest/{normalize,token,body,kafka}.ts` + `ingest.test.ts` + `kafka.kafka.test.ts`, `apps/web/src/demo/{scenarios,send}.ts` + `scenarios.test.ts`, `apps/web/e2e/ingest.spec.ts`, `contracts/v1/{security-event,normalized-event}.schema.json`, `contracts/v1/examples/{security-event,normalized-event}.json`, `fixtures/scenarios/scenario-{a,b,c}.json`, `progress/handoffs/phase-03.md`.
Modified: `.env.example`, `README.md`, `apps/web/{README.md,package.json,package-lock.json,next.config.ts,playwright.config.ts,vitest.config.ts}`, `apps/web/src/app/api/events/route.ts`, `apps/web/src/server/api.ts`, `apps/web/src/db/reference-data.ts`, `apps/web/src/server/auth/password.test.ts` (timeout), `apps/web/e2e/{support,prepare-db,shell.spec}.ts`, `contracts/v1/README.md`, `fixtures/README.md`, `docs/{12_DEMO_SCENARIOS,14_API_CONTRACTS,16_ENVIRONMENT}.md`, `scripts/{verify.py,README.md}`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-02.md` (receiver acceptance).

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 23 checks, 0 failed, 0 warnings, exit 0 |
| `npm test` (unit) | 78 passed (contract drift + example pair, 16 rejection cases, normalization/IP canonicalization/skew, token, body limits incl. chunked bodies, `__proto__` reviver, scenarios, `sendEvents` stop-on-failure) |
| `npm run test:kafka` | 2 passed: publish → consume with key/headers/contract-valid value; unreachable broker rejects within the bound |
| `npm run test:db` | 40 passed (unchanged) |
| `npm run test:e2e` | 16 passed (9 shell + 7 ingest): token and session ingestion land in Kafka normalized; 401 ×3; 415, 413, invalid JSON, contract issue paths, future timestamp, `__proto__`; demo scenario A → 9 events in Kafka keyed `alice`; degraded server (DB down): token ingestion 202 and in Kafka, session ingestion 503 |
| E2E server logs | 0 query-parameter leaks, 0 unhandled errors |
| Operator run: `next start` on 3005 + `npm run demo:send -- A/B/C` | 9 + 4 + 4 accepted; `security-events` = 17 messages; app log 17 × `ingest.accepted`, no errors |
| Topic isolation | after the full verify run (incl. E2E and Kafka tests) `security-events` still = 17 |
| `npm audit --omit=dev` | 0 vulnerabilities |

## Decisions
D-040 (Confluent Kafka client), D-041 (ingest auth), D-042 (zod → generated JSON Schema), D-043 (event semantics, normalization, Kafka message), D-044 (demo generator), D-045 (isolated test topics). D-038 also gained a note on the `eslint-plugin-import` peer warning.

## Known issues / limitations
- zod 4 silently drops `__proto__` keys, so the explicit rejection lives in the route's JSON reviver (`parseJsonBody`). Other producers of `normalized-event` must not rely on zod alone for that rule.
- The API does no deduplication: re-sending a scenario with the same `--base` publishes duplicate event IDs, deduplicated by the worker via `external_event_id` (D-014). Phase 04 must keep that guarantee.
- No ingestion rate limiting; the token is a single shared secret (no rotation or multiple producers). Revisit in Phase 12.
- `security-events-e2e` and `security-events-test` grow by a few messages per run (consumers filter by `event_id`). Recreating the Kafka container clears all topics.
- `npm install` prints an ERESOLVE peer warning for `eslint-plugin-import` (ESLint ≤9 peer); harmless (D-038).
- Scenario C's "unusual time" depends on `--base`; Phase 04 features should be tested with a fixed base.

## Deferred work
None from Phase 03 scope.

## Next-agent requirements (Phase 04)
1. Verify this handoff and mark Phase 03 `COMPLETE` or `REJECTED`.
2. Record before coding:
   - the Isolation Forest feature list and alert threshold (open decision);
   - the Python Kafka consumer library (confluent-kafka, mirroring D-040) and Python DB access (psycopg 3, D-010);
   - `sentinelx_app` LOGIN for the worker (`APP_DATABASE_URL`, D-035) vs. a separate role.
3. The worker consumes `security-events`, validates each message against `contracts/v1/normalized-event.schema.json` (contract test on `contracts/v1/examples/`), and persists `security_events` with `ON CONFLICT (external_event_id) DO NOTHING`. Invalid messages must not crash the consumer.
4. The 17 demo events already queued in `security-events` are the first real input; their `occurred_at` values are from 2026-10-08.

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:migrate && npm run db:seed && npm run db:roles)
python scripts/verify.py                      # expect: 23 checks: 0 failed, exit 0
# Operator path (needs INGEST_API_TOKEN in .env):
(cd apps/web && npm run build && npx next start --port 3005) &   # separate terminal
(cd apps/web && npm run demo:send -- A --url http://localhost:3005)   # expect demo.done accepted 9
```

## Rollback
`git revert <phase-03 commit>` restores Phase 02 (`b428834`); `POST /api/events` returns to its 501 placeholder. No database changes in this phase. Kafka: `docker compose rm -sf kafka && docker compose up -d` empties all topics (`kafka-init` recreates `security-events`).
