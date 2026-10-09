# Phase 13 — Testing & Demo — Handoff

PHASE: 13
STATUS: READY_FOR_NEXT_PHASE
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `3f2769f` (Phase 12). Phase 13 is the commit that adds this file.
PREVIOUS PHASE: 12 accepted as COMPLETE at the start of this phase (db:roles ok, verify.py 24/24, Qdrant 401 without the key, verify self-test OK).

## Objective
Unit, integration, E2E, demo fixtures, README and demo instructions. Exit: clean-machine setup and demo are reproducible.

## Completed work
- **Whole stack in Compose** (D-079): `docker compose --profile app up -d --build` adds `setup` (migrate, seed, roles), `knowledge` (ingestion), `ai` (internal only, healthcheck), `detection` and `web` (127.0.0.1:3000), sequenced with `depends_on` conditions. Plain `docker compose up -d` is unchanged.
- **Images** (repo-root context; `.dockerignore` keeps `.env`, `.git`, dependencies and caches out):
  - `apps/web/Dockerfile`: multi-stage, production dependencies only at runtime, runs as `node`;
  - `services/detection/Dockerfile`: model trained at build time, runs as uid 10001;
  - `services/ai/Dockerfile`: CPU torch from the PyTorch index, the pinned embedding model baked in, offline at runtime, uid 10001.
- **`scripts/container-env.sh`**: the entrypoint rewrites only the database URLs' host:port to `postgres:5432`, keeping `.env` the single source of credentials (self-checked).
- **AI service**: `AI_SERVICE_HOST` override (default 127.0.0.1; 0.0.0.0 only inside the Compose network, unpublished).
- **Demo**:
  - `docs/22_DEMO.md` is the clean-machine guide; the README leads with it, and docs/12 and docs/16 link to it;
  - `apps/web/playwright.demo.config.ts` + `demo-check/demo.spec.ts` is the automated full-stack demo (D-080).
- **Testing**:
  - docs/08 coverage map (every test-plan item and negative case → test files);
  - `verify.py` runs pytest with `--tb=line -rf` so failure reasons survive the summary;
  - the live investigation test tolerates a transient connect timeout in its own status poll.
- **Security checklist re-check** for containers: §3.5 (no secrets in images), §3.6 (whole `.env` per container, accepted), §9.3 (only `web` published), §9.5 (unprivileged containers).

## Files changed
Added:
- `.dockerignore`, `scripts/container-env.sh`
- `apps/web/Dockerfile`, `services/detection/Dockerfile`, `services/ai/Dockerfile`
- `apps/web/playwright.demo.config.ts`, `apps/web/demo-check/demo.spec.ts`
- `docs/22_DEMO.md`, `progress/handoffs/phase-13.md`

Modified:
- `docker-compose.yml`, `scripts/{verify.py,README.md}`
- `services/ai/sentinelx_ai/__main__.py`, `services/ai/tests/integration/test_investigation_live.py`
- `README.md`, `apps/web/README.md`
- `docs/{08_TEST_PLAN,12_DEMO_SCENARIOS,16_ENVIRONMENT,21_SECURITY_CHECKLIST}.md`
- `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-12.md` (receiver acceptance)

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 24 checks, 0 failed, 0 warnings (final run). An earlier run failed once; its `--tb=line` output showed a connect timeout in the live test's own poll, which is now tolerated within the deadline |
| `services/ai` `pytest` (full, standalone) | 200 passed |
| `docker compose --profile app build` | web 1.55 GB, detection 606 MB (model trained in the build), ai 2.28 GB (CPU torch, model baked) |
| Container access to host Ollama | `host.docker.internal:11434` → 200 |
| `container-env.sh` self-check | localhost/127.0.0.1 URLs rewritten to `postgres:5432` (query string kept); other hosts untouched; unset variables stay unset |
| **Clean start**: `docker compose -p sentinelxclean --profile app up -d` on new empty volumes | up in 73 s; `setup` (9 IPs, 11 techniques, roles) and `knowledge` (19 documents) exited 0; `ai` healthy with the model loaded offline; `/login` 200; port 8000 not reachable from the host |
| Analyst creation and `demo:send` exactly as documented | analyst created; scenario B: 4 × 202, stored, 0 alerts, no incident |
| **Demo check** `npx playwright test -c playwright.demo.config.ts` | passed in 1.8 min: incident with 9 events and 5 alerts, risk 88 CRITICAL; investigation completed in 81 s; CRITICAL verdict citing 18 existing evidence IDs, T1078/T1110, no findings; screenshot reviewed (full page with real trace, evidence, MITRE and verdict) |
| Teardown | `down -v` removed the clean project's volumes (0 left); dev infrastructure restarted healthy |

## Decisions
D-079 (whole stack in Compose: services, entrypoint rewrite, images, Ollama on the host, the cross-platform model finding, whole `.env` per container); D-080 (the clean-machine guide, the demo check, the measured clean start, `--tb=line` and the poll fix).

## Known issues / limitations
- **The Isolation Forest is deterministic per platform only.** The Linux container trains version `767255fe77ca` (risk 88 on scenario A) and the Windows host `bf36c4b809a6` (risk 90). Both are CRITICAL with the same signals; `alerts.model_version` records which.
- **Image sizes** total about 4.4 GB; the first build took about 15 minutes on the reference machine.
- **Linux hosts** must start Ollama with `OLLAMA_HOST=0.0.0.0` so containers can reach it (documented).
- **Every app container receives the whole `.env`** (accepted local risk, docs/21 3.6).
- **Memory.** The reference machine ran at 0.1–1.5 GB available. Investigations were slower (81–113 s), and one gate run hit a transient connect timeout in a test poll.
- **The demo check is outside `verify.py`.** It needs the running stack, an analyst and Node with Playwright.

## Deferred work
None from Phase 13 scope.

## Next-agent requirements (Phase 14)
1. Verify this handoff and mark Phase 13 `COMPLETE` or `REJECTED`.
2. Phase 14 (Interview Polish):
   - an architecture diagram of the real system (host and Compose topologies);
   - tradeoffs (why each component, alternatives rejected; DECISIONS.md is the source);
   - performance notes (measured numbers are in D-056, D-064, D-070, D-080: investigation 49–113 s, cold model load 19–40 s, retrieval about 0.1 s per query, clean start 73 s);
   - limitations (docs/17, docs/21 accepted risks);
   - interview Q&A.
   Exit: every major component has a defensible why.

## Verification commands
```sh
git status                                    # clean
docker compose up -d && (cd apps/web && npm run db:roles)
python scripts/verify.py                      # expect: 24 checks: 0 failed
# Clean-machine demo (docs/22): full stack on a throwaway project with new volumes
docker compose stop
docker compose -p sentinelxclean --profile app up -d --build
docker compose -p sentinelxclean --profile app run --rm -e ANALYST_PASSWORD='<12+ chars>' setup npm run --silent analyst:create -- demo@sentinelx.local "Demo"
(cd apps/web && DEMO_EMAIL=demo@sentinelx.local DEMO_PASSWORD='<same>' npx playwright test -c playwright.demo.config.ts)
docker compose -p sentinelxclean --profile app down -v && docker compose up -d
```

## Rollback
- Code: `git revert <phase-13 commit>` restores Phase 12 (`3f2769f`). The app services are profile-gated, so the infrastructure-only workflow never depended on them.
- Images: `docker image rm sentinelx-web:local sentinelx-detection:local sentinelx-ai:local`.
- Data: no schema or data change in the dev database.
