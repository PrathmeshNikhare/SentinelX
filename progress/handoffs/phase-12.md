# Phase 12 — Security & Reliability — Handoff

PHASE: 12
STATUS: COMPLETE (receiver accepted 2026-10-09 at Phase 13 start: db:roles ok, verify.py 24/24, Qdrant 401 without key, verify self-test OK)
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `1e59907` (Phase 11). Phase 12 is the commit that adds this file.
PREVIOUS PHASE: 11 accepted as COMPLETE at the start of this phase (db:roles ok, verify.py 24/24 incl. the E2E walkthrough), after Docker Desktop was restarted by the user.

## Objective
Auth hardening, secrets, input validation, audit logging, dependency review, failure handling. Exit: the security checklist passes.

## Completed work
- **Security checklist** `docs/21_SECURITY_CHECKLIST.md`: 45 items across 11 areas, each with its implementation and test or command evidence. Every item is PASS except 5 ACCEPTED risks with reasons. docs/11 links to it.
- **Login throttling** (D-075): `src/server/auth/login-throttle.ts`, in-memory and per normalized email: 5 failures per 15 minutes, applies to unknown emails, capped at 10,000 entries. Wired into the login action.
- **Security headers** (D-076): `next.config.ts` sends the CSP (the Next.js no-nonce guide; `unsafe-eval` only in development), nosniff, DENY framing, no-referrer and a Permissions-Policy.
- **Audit and AI boundary** (D-077):
  - `ingest.unauthorized` and `ai.unauthorized` events, with no token logged;
  - the AI service answers 411 for bodies without Content-Length, completing the 16 KiB cap and closing the Phase 06 `ponytail:`;
  - a database outage during verdict validation fails the run and keeps the model's answer (`validation_unavailable`), closing the Phase 10 gap; the web labels the new code.
- **Qdrant API key** (D-078):
  - Compose `QDRANT__SERVICE__API_KEY` from `QDRANT_API_KEY` (required);
  - `qdrant_client(url, timeout, api_key)`;
  - `Settings.qdrant_api_key` and the ingestion CLI validated by `validate_secret` (generalized from the service-token check);
  - `verify.py` sends the key (stdlib `env_value`, with a self-test).
  The reference `.env` received a generated key by append (never read or printed). The Qdrant container was recreated with its volume kept: 19/19 documents remain.
- **Reviews:** dependency review (npm prod 0, dev 9 accepted; OSV detection 0/29, AI 0/94) and a secret scan of the git history (14 commits, clean).

## Files changed
Added:
- `docs/21_SECURITY_CHECKLIST.md`
- `apps/web/src/server/auth/{login-throttle,login-throttle.test}.ts`, `apps/web/e2e/security.spec.ts`
- `progress/handoffs/phase-12.md`

Modified:
- `apps/web/next.config.ts`, `apps/web/src/app/login/actions.ts`, `apps/web/src/server/api.ts`, `apps/web/src/lib/investigation-view{,.test}.ts`
- `services/ai/sentinelx_ai/{app,config,graph,knowledge}.py`
- `services/ai/tests/{test_app,test_contracts_and_config,test_graph,test_knowledge}.py`, `services/ai/tests/integration/{conftest,test_investigation_live,test_knowledge_live}.py`
- `services/ai/README.md`
- `scripts/{verify,test_verify}.py`
- `docker-compose.yml`, `.env.example`, `README.md`
- `docs/{11_SECURITY_RULES,16_ENVIRONMENT}.md`
- `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-11.md` (receiver acceptance)

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 24 checks, 0 failed, 0 warnings (E2E 23 incl. `security.spec.ts`; the knowledge check with the API key) |
| `python -m unittest scripts.test_verify` | 6 passed (incl. `env_value`) |
| `services/ai` unit | 169 passed (new: 411 for chunked bodies without Content-Length; validation outage keeps the answer; 4 weak/missing Qdrant key cases) |
| `services/ai` live retrieval (`test_knowledge_live.py`) | 9 passed with the key |
| Web unit | login throttle 4 tests (block, window reset, success reset, memory bound); label for `validation_unavailable` |
| Web E2E `security.spec.ts` | headers on `/login` and `/api/incidents` (CSP without `unsafe-eval`, nosniff, DENY, no-referrer, no `X-Powered-By`); login renders with no CSP violations; an unknown email is throttled on attempt 6 (case-normalized key) |
| Qdrant enforcement | `/readyz` 200 without the key; `/collections` 401 without it |
| Mutations (restored byte-identical) | throttle disabled → 2 unit failures; 411 check removed → `test_app` fails; Qdrant key validation removed → 4 failures |
| Scans | `npm audit --omit=dev` 0 / 136; `npm audit` 9 (dev-only, accepted); OSV detection 0 / 29, AI 0 / 94; git history (14 commits) and diff: no secrets; no leftover test databases |

## Decisions
D-075 (login throttling), D-076 (security headers), D-077 (audit events, 411 body rule, validation outage), D-078 (Qdrant API key).

## Known issues / limitations (accepted risks, docs/21)
- **Local role passwords** in `.env.example` (`*_local`): PostgreSQL is reachable on 127.0.0.1 only.
- **The CSP allows `'unsafe-inline'` scripts** (Next.js hydration without nonces).
- **Plain HTTP between local services** (AI token, Qdrant key) over loopback.
- **9 dev-only npm advisories** (`drizzle-kit`'s bundled esbuild, `eslint-config-next`'s glob chain); the fixes would be major downgrades.
- **Single instance assumed** for the login throttle and run abandonment (D-023).
- **No per-IP throttle:** the client IP is not reliable without a trusted proxy.

## Deferred work
None from Phase 12 scope. Clean-machine reproducibility (containerizing web, worker and AI, plus the Linux CPU torch index) is Phase 13.

## Next-agent requirements (Phase 13)
1. Verify this handoff and mark Phase 12 `COMPLETE` or `REJECTED`.
2. Phase 13 (Testing & Demo): clean-machine setup and demo reproducibility, README and demo instructions, demo fixtures. Per D-023, add the web app, detection worker and AI service to Compose:
   - install torch from the PyTorch CPU index on Linux (D-070);
   - provide the model cache or a download step;
   - wire `QDRANT_API_KEY` and `AI_SERVICE_TOKEN` through.
   Keep every port on 127.0.0.1.
3. Run the full demo end to end (ingest scenario A → detection → incident → Investigate → grounded verdict in the UI) and record it.
4. Re-run the security checklist evidence after the Compose changes (service binding, secrets in the container environment).

## Verification commands
```sh
git status                                    # clean
# .env must contain QDRANT_API_KEY (random, 32+ chars) — see .env.example
docker compose up -d
(cd apps/web && npm run db:roles)
python scripts/verify.py                      # expect: 24 checks: 0 failed
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:6333/collections   # expect 401 without the key
python -m unittest scripts.test_verify         # expect 6 OK
```

## Rollback
- Code: `git revert <phase-12 commit>` restores Phase 11 (`1e59907`).
- Qdrant key: remove `QDRANT__SERVICE__API_KEY` from Compose and run `docker compose up -d qdrant`; `QDRANT_API_KEY` in `.env` may stay.
- The login throttle is in memory and clears on restart. No schema or data changes.
