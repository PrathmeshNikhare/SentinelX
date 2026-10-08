# Phase 05 — Correlation & Incidents — Handoff

PHASE: 05
STATUS: READY_FOR_NEXT_PHASE
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `465d878` (Phase 04). Phase 05 is the commit that adds this file.
PREVIOUS PHASE: 04 accepted as COMPLETE at the start of this phase (verify.py 23/23, detection pytest 57/57, retraining reproduced the model version).

## Objective
Alert persistence, bounded correlation, incident lifecycle. Exit: expected incidents; duplicate/correlation tests.

## Completed work
- Alerts (D-052): for `risk ≥ 40` the worker writes `alerts` in the same per-event transaction (idempotent on `event_id`). `reasons_json` holds the signals, the R/A/P/C components and the formula.
- Correlation (D-053), in `sentinelx_detection/correlation.py` (pure plan, titles, reasons) plus repository SQL:
  - per-user grouping over a 60-minute event-time window against the most recent non-resolved incident (row-locked);
  - non-alerting events in the window are linked for a complete timeline;
  - lookback links the user's unlinked events from the previous hour when an incident is created;
  - risk, severity, primary IP, start and title are recomputed from linked rows (idempotent);
  - replayed events never move.
- Lifecycle (D-054):
  - `src/lib/incident-lifecycle.ts`: transition table and labels;
  - `transitionIncident()`: row lock plus check plus update in one transaction;
  - `PATCH /api/incidents/:id` (strict body, capped size, `__proto__`-safe parser reused from Phase 03);
  - buttons on the incident page via a Server Action;
  - `incident.status_changed` structured log with analyst id.
- Dev backfill (D-055): the topic (34 events: A, B, C plus a second A, B and C sent at 18:3x UTC) was replayed with group `backfill-phase05`. Result: 4 incidents (alice CRITICAL 90 ×2, carol HIGH 60 and MEDIUM 54), 12 alerts, bob none. The long-running worker was restarted on `sentinelx-detection` with the new code.

## Files changed
Added: `services/detection/sentinelx_detection/correlation.py`, `services/detection/tests/test_correlation.py`, `apps/web/src/lib/incident-lifecycle.ts` + `.test.ts`, `apps/web/src/app/(console)/incidents/[id]/actions.ts`, `progress/handoffs/phase-05.md`.
Modified: `services/detection/sentinelx_detection/{pipeline,repository,worker}.py`, `services/detection/tests/integration/test_worker.py`, `services/detection/README.md`, `apps/web/src/app/api/incidents/[id]/route.ts`, `apps/web/src/server/queries/incidents.ts`, `apps/web/src/app/(console)/incidents/[id]/page.tsx`, `apps/web/e2e/shell.spec.ts`, `docs/{14_API_CONTRACTS,16_ENVIRONMENT}.md`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-04.md` (receiver acceptance). No schema or migration change.

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 23 checks, 0 failed, 0 warnings |
| detection `pytest` unit | 69 passed: Phase 04's 55 plus 14 correlation tests (window edges, the 8-row plan table, title priority, alert reasons recompute the risk) |
| detection `pytest tests/integration` | 3 passed (about 50 s): alerts equal the pure pipeline's `should_alert` set with matching risk, severity and reasons; incidents A/C/B as designed (A started at its first event via lookback); exact duplicate and event_id reuse cause no duplicates; full replay leaves events, signals, alerts, incidents and links byte-identical; burst after the window gives a 2nd incident, and a burst inside the window of a resolved incident gives a 3rd with the resolved one untouched |
| Mutation: drop the `status <> 'resolved'` filter | exactly `test_correlation_window_and_resolved_incidents` failed; file restored byte-identical |
| web `npm test` | 81 passed (+3 lifecycle) |
| web `npm run test:e2e` | 17 passed (+ lifecycle: buttons open → investigating → resolved; PATCH 409 `current: resolved`, 400 bogus status, 404 unknown, 200 reopen, 400 extra field; PATCH without session 401) |
| Dev backfill `worker --group backfill-phase05 --idle-exit 15` | 34 replayed: 4 create, 14 link, 16 none, giving 4 incidents and 12 alerts as listed above |
| Gate scans | 0 leftover test DBs/topics; `security-events` = 34; no secrets; no schema drift; live worker started |

## Decisions
D-052 (alert persistence and reasons), D-053 (per-user 60-minute correlation; resolves the open decision), D-054 (lifecycle), D-055 (dev backfill by replay).

## Known issues / limitations
- No IP-keyed cross-user correlation (password spraying gives one incident per targeted user), deferred in D-053.
- Status changes are logged, not stored in an audit table (Phase 12).
- The incident page shows linked events and lifecycle buttons only. Alerts, signals and reasons are in the DB and API but not rendered until Phase 11.
- Incidents never auto-close; resolving is manual.
- The risk-weight label in `reasons_json.formula` is rendered from constants (e.g. `0.45R`); if weights change, old alerts keep the formula they were scored with.

## Deferred work
None from Phase 05 scope.

## Next-agent requirements (Phase 06)
1. Verify this handoff and mark Phase 05 `COMPLETE` or `REJECTED`.
2. Record before coding: the Ollama model (`.env.example` says `llama3.2:3b`, while the reference machine has `gemma4:e2b`; open decision) and the structured-output mode.
3. Phase 06: FastAPI skeleton, health endpoint, `AI_SERVICE_TOKEN` internal auth (D-022, D-025), Ollama adapter, verdict Pydantic schema plus `contracts/v1` investigation/verdict contracts (D-011, D-042), AI DB roles LOGIN when first used (D-031).
4. `POST /api/incidents/:id/investigate` (Phases 06–08) should move an `open` incident to `investigating` through `transitionIncident()`; do not bypass the lifecycle rules.

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:migrate && npm run db:seed && npm run db:roles)
python scripts/verify.py                      # expect: 23 checks: 0 failed
(cd services/detection && .venv/Scripts/python -m pytest -q)   # expect: 72 passed
```

## Rollback
`git revert <phase-05 commit>` restores Phase 04 (`465d878`): the worker stops writing alerts and incidents, and the lifecycle API and buttons disappear. To remove Phase 05 dev data as the owner: `DELETE FROM incident_alerts; DELETE FROM incident_events; DELETE FROM incidents; DELETE FROM alerts;` (the app role cannot delete).
