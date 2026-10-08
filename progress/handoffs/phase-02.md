# Phase 02 — Web Shell — Handoff

PHASE: 02
STATUS: READY_FOR_NEXT_PHASE
GATE: `/verify-phase` APPROVED (2026-10-08)
BASE COMMIT: `0679112` (Phase 01). Phase 02 is the commit that adds this file.
PREVIOUS PHASE: 01 accepted as COMPLETE at the start of this phase (verify.py 21/21, test:db 32/32 reproduced).

## Objective
Next.js App Router console with an auth boundary, navigation, incident list/detail shell and API placeholders; loading, error, empty and degraded states; no fake metrics.

## Completed work
- Auth (D-034): scrypt password hashing (Node built-in), server-side `analyst_sessions` (SHA-256 token hashes, 8 h expiry, revocation via `revoked_at`), HttpOnly/SameSite=Lax cookie (Secure in production), Server Action login/logout, generic failure message with timing-equalized unknown-email path, `src/proxy.ts` optimistic redirect plus a DB-validated session check in every page and API route.
- DB: migration `0002` (`analyst_sessions`) and `0003` (grants: `sentinelx_app` SELECT/INSERT/UPDATE only). The web app connects as `sentinelx_app` (`APP_DATABASE_URL`, D-035). New CLI commands: `npm run db:roles` (enable LOGIN with the URL's password) and `npm run analyst:create` (password via `ANALYST_PASSWORD`).
- UI (D-036): Tailwind v4 + shadcn/ui (button, input, label, table, badge), compact sidebar, header with analyst and sign-out. Pages:
  - overview: real counts, open incidents by severity CRITICAL→LOW, events and alerts in the last 24 h, recent incidents;
  - incidents list;
  - incident detail: header, risk, identity, timestamps, linked events;
  - events.
  Plus `loading.tsx`, `error.tsx`, not-found pages, explicit empty states, a `DataUnavailable` panel, and a full-page `ServiceUnavailable` when the session cannot be verified.
- API: `GET /api/incidents`, `GET /api/incidents/:id` (real); `POST /api/events` (501, Phase 03); `POST /api/incidents/:id/investigate` and `GET /api/investigations/:id` (501, Phases 06–08). JSON errors 401/404/501/503.
- Logging: JSON lines; `describeError` drops Drizzle bound parameters (no emails, token hashes or password hashes in logs).
- Tests: unit (password, session-token helpers, IDs, UTC format, log sanitization), DB integration (sessions, analyst creation, session grants), Playwright E2E against a production build with healthy and degraded servers (D-037). `verify.py` gained `web: e2e (build + playwright)` (22 checks).
- Security fix during the phase: `next` 16.3.6 → 16.3.8 (high-severity advisories, D-038).
- Bugs found and fixed during verification:
  - `load()` swallowed Next's control-flow errors (fixed with `unstable_rethrow`);
  - degraded pages threw unhandled errors whose logs contained query parameters (fixed with three-way session state and sanitized logging);
  - the email field was cleared after a failed sign-in (React 19 form reset; the email is now echoed into `defaultValue`).

## Files changed
Added: `apps/web/{next.config.ts,postcss.config.mjs,playwright.config.ts,components.json,AGENTS.md,CLAUDE.md}`, `apps/web/drizzle/{0002_analyst_sessions.sql,0003_session_grants.sql,meta/0002_snapshot.json,meta/0003_snapshot.json}`, `apps/web/src/proxy.ts`, `apps/web/src/app/**` (layout, globals.css, not-found, login/, (console)/, api/), `apps/web/src/components/{ui,console}/**`, `apps/web/src/lib/{utils,ids,format}.ts` + `lib.test.ts`, `apps/web/src/server/{db,load,log,api}.ts` + `log.test.ts`, `apps/web/src/server/auth/{password,session,session-store}.ts` + `password.test.ts`, `apps/web/src/server/queries/{incidents,events,overview}.ts`, `apps/web/src/db/admin.ts`, `apps/web/e2e/{support,prepare-db,global-teardown}.ts` + `shell.spec.ts`, `progress/handoffs/phase-02.md`.
Modified: `.env.example` (+`APP_DATABASE_URL`, −`SESSION_SECRET`), `README.md`, `apps/web/{README.md,package.json,package-lock.json,tsconfig.json,eslint.config.js}`, `apps/web/drizzle/meta/_journal.json`, `apps/web/src/db/{schema,env,cli,db.db.test}.ts`, `docs/{04_DATA_MODEL,14_API_CONTRACTS,16_ENVIRONMENT}.md`, `scripts/{verify.py,README.md}`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-01.md` (receiver acceptance).

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 22 checks, 0 failed, 0 warnings, exit 0 |
| `npm test` (unit) | 38 passed |
| `npm run test:db` | 40 passed (incl. session lifecycle, analyst creation rules, session grants, AI roles still NOLOGIN) |
| `npm run test:e2e` | 9 passed: unauthenticated redirects; API 401 ×5; wrong password → generic message, email kept, same-page retry succeeds; sign-in + cookie flags (HttpOnly, Lax, Secure, /); empty states and zero counts; not-found (unknown and malformed id); API 200/404/501 ×3; populated list/detail/API; sign-out + revoked-token replay rejected (page and API); degraded sign-in message; degraded console "Service unavailable" + API 503 |
| E2E server logs | 0 occurrences of query `params`, 0 unhandled errors |
| Lint probes (`<a>` to internal page, conditional hook) | both flagged (rules active); probe removed |
| Dev server smoke (`next dev` on 3005) | `/login` 200, `/` 307 → `/login`, `/api/incidents` 401 JSON; server stopped |
| Screenshots (login error, overview, incidents, detail) | reviewed: dense console, text-labelled badges, mono IDs/IPs/UTC, no decorative styling |
| `npm audit --omit=dev` | 0 vulnerabilities |
| Scans | every console page has `requireSession()`, every API route has `withSession(`; no gradient/purple/glow/blur classes; no secrets beyond test fixtures; `services/` untouched |

## Decisions
D-034 (auth/sessions), D-035 (web connects as `sentinelx_app`), D-036 (UI structure and states), D-037 (Playwright production-build E2E), D-038 (dependency pins, Next security upgrade, shadcn adjustments, ESLint 10 workaround, `.env` bundling and log-sanitization rules), D-039 (commit Next-generated `AGENTS.md`/`CLAUDE.md`).

## Known issues / limitations
- `loading.tsx` and `error.tsx` are implemented and build-verified but have no automated test: there is no deterministic trigger without adding test hooks to production code.
- No login rate limiting or lockout (Phase 12, D-034). Expired and revoked session rows are never deleted (the app role has no DELETE); add a retention job in Phase 12.
- The proxy only checks cookie presence; correctness depends on each page/route calling `requireSession()` / `withSession()`. New routes must follow this (gate scan above).
- In `next dev` over http the cookie is not `Secure` (production only).
- Dev-only audit advisories remain (drizzle-kit esbuild; eslint-config-next → braces), see D-033/D-038.
- `verify.py` now needs Playwright Chromium (`npx playwright install chromium`) and free ports 3100/3101; it takes about 3 minutes.
- No analyst account exists in the dev database; create one with `npm run analyst:create` (docs/16).

## Deferred work
None from Phase 02 scope.

## Next-agent requirements (Phase 03)
1. Verify this handoff and mark Phase 02 `COMPLETE` or `REJECTED`.
2. Record before coding:
   - the TypeScript Kafka client (open decision);
   - how `POST /api/events` authenticates: the analyst session only, or also a service credential for the deterministic demo generator (currently session-only via `withSession`).
3. Define `contracts/v1/security-event.schema.json` + examples (D-011) and validate at the API boundary; map `timestamp` → `occurred_at` (D-030).
4. Kafka key = `user_id` (D-014); the API does not write to PostgreSQL.
5. Replace the `POST /api/events` 501 placeholder and its E2E expectation.

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:migrate && npm run db:seed && npm run db:roles)
python scripts/verify.py                      # expect: 22 checks: 0 failed, exit 0
(cd apps/web && npm test && npm run test:db && npm run test:e2e)   # 38 / 40 / 9 passed
```

## Rollback
`git revert <phase-02 commit>` restores Phase 01 (`0679112`). Database: migrations 0002/0003 add only `analyst_sessions` and its grant; drop with `DROP TABLE analyst_sessions;` and delete the two rows from `drizzle.__drizzle_migrations`, or `docker compose down -v` and re-migrate. `ALTER ROLE sentinelx_app NOLOGIN;` undoes `db:roles`.
