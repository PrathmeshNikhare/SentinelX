# Phase 01 — Database — Handoff

PHASE: 01
STATUS: COMPLETE (receiver accepted 2026-10-08 at Phase 02 start: verify.py 21/21, test:db 32/32, key files tracked, no DELETE/TRUNCATE grants)
GATE: `/verify-phase` APPROVED (2026-10-08)
BASE COMMIT: `62a51d0` (Phase 00). Phase 01 is the commit that adds this file.
PREVIOUS PHASE: 00 accepted as COMPLETE at the start of this phase (handoff commands reproduced; see `phase-00.md`).

## Objective
Drizzle + PostgreSQL schema (docs/04), migrations, least-privilege roles (D-022/D-031), reference-data seeds (D-020/D-032), with clean-migration, CRUD and role-permission tests.

## Completed work
- `apps/web/src/db/schema.ts`: 13 tables, 6 enums, FKs (no cascades), check constraints (scores 0–100, step_index ≥ 0, technique ID format), unique keys (`external_event_id`, alert per event, signal per event+rule, trace step per run, knowledge source+external_id), indexes per docs/04. Database-generated prefixed IDs (D-030).
- `apps/web/drizzle/0000_init.sql` (generated) and `0001_roles.sql` (hand-written): NOLOGIN roles `sentinelx_app`, `sentinelx_ai_tools` (SELECT-only, no analysts or investigation records), `sentinelx_ai_writer` (INSERT/UPDATE runs, INSERT-only trace and evidence). No DELETE/TRUNCATE/CREATE for any role.
- `apps/web/src/db/{env,migrate,seed,cli,reference-data}.ts`: `.env` loading, migrator, idempotent sync of `ip_reputation`/`mitre_techniques` from fixtures (upsert + delete removed rows), CLI with JSON-line logs (connection string never logged), fixture validators (synthetic-IP-only, enum, score and technique-ID checks).
- `fixtures/ip_reputation.json` (9 synthetic IPs from RFC 1918/5737) and `fixtures/mitre_techniques.json` (11 ATT&CK techniques, own descriptions, version recorded).
- Tests: `reference-data.test.ts` (unit, 15 cases) and `db.db.test.ts` (integration, 32 cases on a throwaway database). Vitest projects `unit` / `db`.
- `scripts/verify.py`: new checks `web: schema matches migrations` (drift detection) and `web: db integration`; `web: vitest` renamed `web: vitest unit`. 21 checks total.
- Docs: docs/04 rewritten to match the schema and roles; docs/07 Phase 01 wording (D-032); docs/16 setup includes `db:migrate`/`db:seed` plus a Database section; README, apps/web, fixtures and scripts READMEs; decisions D-030–D-033.

## Files changed
Added: `apps/web/drizzle.config.ts`, `apps/web/vitest.config.ts`, `apps/web/drizzle/{0000_init.sql,0001_roles.sql,meta/_journal.json,meta/0000_snapshot.json,meta/0001_snapshot.json}`, `apps/web/src/db/{schema,env,migrate,seed,cli,reference-data}.ts`, `apps/web/src/db/{reference-data.test.ts,db.db.test.ts}`, `fixtures/{ip_reputation,mitre_techniques}.json`, `progress/handoffs/phase-01.md`.
Modified: `.gitignore` (`.drift-check/`), `README.md`, `apps/web/{README.md,package.json,package-lock.json,tsconfig.json}`, `docs/{04_DATA_MODEL,07_PHASES,16_ENVIRONMENT}.md`, `fixtures/README.md`, `scripts/{README.md,verify.py}`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-00.md` (receiver acceptance).

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 21 checks, 0 failed, 0 warnings, exit 0 |
| `npm test` (apps/web, unit) | 16 passed (1 toolchain + 15 fixture validation) |
| `npm run test:db` | 32 passed: exact table set, migration journal + re-run no-op, CRUD, 23505/23503/23514/22P02 constraint codes, detection→evidence chain, seed counts + idempotency + stale-row removal, 25 role assertions, roles NOLOGIN |
| Mutation: extra `GRANT DELETE ON security_events TO sentinelx_ai_tools` | exactly that assertion failed (1 failed, 31 passed); file restored byte-identical |
| Drift probe: add a column to schema.ts without a migration | drift check generated `0002_*.sql` → would FAIL; schema restored |
| `docker compose down -v` → up → `db:migrate` → `db:seed` | 13 tables, 2 migrations, 9 IPs, 11 techniques, 3 roles NOLOGIN |
| Leftover test databases after runs | 0 |
| `npm audit --omit=dev` | 0 vulnerabilities (4 moderate dev-only, see known issues) |

## Decisions
D-030 (prefixed DB-generated IDs, `occurred_at`), D-031 (NOLOGIN roles, append-only writer), D-032 (reference seeds only; demo events from Phase 03), D-033 (tool pins, Node type stripping, drift check, audit acceptance).

## Known issues / limitations
- `npm audit`: 4 moderate advisories in drizzle-kit's dev-only `@esbuild-kit` → esbuild ≤0.24.2 (dev-server advisory; not exercised). Accepted in D-033; re-check when upgrading drizzle-kit.
- Roles cannot log in yet (by design, D-031). Phase 03 must add LOGIN + password (from `.env`) for `sentinelx_app` before the API/detection worker connect; Phases 06–07 do the same for the AI roles.
- Migrations and seeds run as the owner/superuser (`DATABASE_URL`). Separating a non-superuser migration role is not done; acceptable for a local prototype.
- Kafka host-side produce/consume is still pending (Phase 03), as noted in Phase 00.
- `drizzle-kit` ignores absolute `--out` paths on Windows; the drift check uses the relative `apps/web/.drift-check/` (gitignored, removed after each run).

## Deferred work
None from Phase 01 scope. Demo/scenario data is intentionally deferred to Phase 03 (D-032).

## Next-agent requirements (Phase 02)
1. Verify this handoff (commands below) and mark Phase 01 `COMPLETE` or `REJECTED`.
2. Record the open Phase 02 decision first: auth/session implementation and password-hashing algorithm (DECISIONS open table).
3. Add Next.js to the existing `apps/web` package (do not run `create-next-app` into it) and extend `eslint.config.js`; keep `allowImportingTsExtensions`/`erasableSyntaxOnly` compatible with Next.js or record the change.
4. Phase 02 reads the database: decide whether the web shell connects as `sentinelx_app` now (then add LOGIN + env password per D-031) and record it.
5. UI must show empty states for incidents/events: there is no seeded demo data (D-032).

## Verification commands
```sh
git status                                   # clean
docker compose up -d
(cd apps/web && npm run db:migrate && npm run db:seed)
python scripts/verify.py                     # expect: 21 checks: 0 failed, exit 0
(cd apps/web && npm run test:db)             # expect: 32 passed
```

## Rollback
`git revert <phase-01 commit>` restores Phase 00 (`62a51d0`). Database: `docker compose down -v` then `up -d` gives an empty PostgreSQL. Roles are cluster-wide and survive `DROP DATABASE`; remove with `DROP ROLE sentinelx_app, sentinelx_ai_tools, sentinelx_ai_writer;` after dropping objects that reference them (or `down -v`).
