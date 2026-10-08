# Phase 04 — Detection Engine — Handoff

PHASE: 04
STATUS: COMPLETE (receiver accepted 2026-10-09 at Phase 05 start: verify.py 23/23, detection pytest 57/57, retraining reproduced iforest-v1-bf36c4b809a6, key files tracked, artifact untracked)
GATE: `/verify-phase` APPROVED (2026-10-08)
BASE COMMIT: `b3d4ed9` (Phase 03). Phase 04 is the commit that adds this file.
PREVIOUS PHASE: 03 accepted as COMPLETE at the start of this phase (verify.py 23/23, `security-events` = 17, contracts regenerate identically).

## Objective
Rules, features, Isolation Forest, deterministic risk engine. Exit: scenarios produce expected signals; risk unit tests pass.

## Completed work
- `services/detection/sentinelx_detection/`:
  - `contract`: jsonschema against the generated contract;
  - `models`, `context`: history windows, with `InMemoryHistory` mirroring the SQL semantics;
  - `rules`: 9 deterministic rules (D-048);
  - `features`: 16 features (D-049);
  - `baseline` + `anomaly` + `train`: seeded synthetic baseline of 7,009 events, IsolationForest(200 trees, seed 42), content-addressed `model_version`, sigmoid anomaly score;
  - `risk`: 0.45·R + 0.25·A + 0.15·P + 0.15·C, half-up rounding, alert threshold 40 (D-050);
  - `pipeline`, `repository` (psycopg, bounded parameterized queries, idempotent upserts, event_id-reuse guard, IPv4-preferring time-bounded `connect()`), `worker` (manual commits, poison-message skip, DB-outage retry without loss, graceful stop, `--idle-exit/--max-messages/--group`).
- Scope (D-046): the worker persists `security_events` and `detection_signals`. Alerts (`should_alert`) and incidents are Phase 05; Phase 05 adds alerts by replaying the topic, since processing is deterministic and idempotent.
- Pinned runtime dependencies frozen in `requirements.txt` (D-047); mypy overrides for untyped libraries; ruff line length 120.
- Design fixes found while tracing scenarios:
  - known IPs come from successful logins only (a brute-forcer's failures no longer whitelist its IP);
  - the baseline includes `known_good` corporate IPs;
  - `model_version` hashes the training matrix (it previously ignored generator changes).
- Operational fix (D-051): psycopg stalled 90 s on `localhost` (`::1`) on Windows. `connect()` now prefers 127.0.0.1 for `localhost` and sets `connect_timeout=10`. `.env` is untouched (protected by the deny rule).
- Dev stack: model trained (`iforest-v1-bf36c4b809a6`, gitignored `services/detection/models/`); the worker processed the 17 queued demo events, so the dev DB has 17 events and 12 signals and the console's Events page shows them.

## Files changed
Added: `services/detection/sentinelx_detection/{config,models,contract,context,rules,features,baseline,anomaly,train,risk,pipeline,repository,worker}.py`, `services/detection/tests/{conftest,test_rules,test_risk,test_features_and_model,test_scenarios}.py`, `services/detection/tests/integration/{__init__,test_worker}.py`, `progress/handoffs/phase-04.md`.
Modified: `.gitignore` (`services/detection/models/`), `README.md`, `docs/16_ENVIRONMENT.md`, `fixtures/README.md`, `services/detection/{README.md,pyproject.toml,requirements.txt}`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-03.md` (receiver acceptance).

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 23 checks, 0 failed, 0 warnings, exit 0 (detection pytest now includes integration) |
| `pytest` unit (services/detection) | 55 passed in about 7 s: 10 rule tests (each fires and misses), 19 risk tests (formula, rounding, ranges, level bands, threshold, monotonicity sweep, B-cannot-alert bound), features/contract/model (determinism, reproducible training, bounded scores, attack > baseline p95, artifact guards), scenarios A/B/C × 2 base times + fixture-normalization guard + determinism |
| `pytest tests/integration` | 2 passed in about 50 s: 20 messages (17 scenario events, invalid JSON, contract violation, event_id reuse) → 20 committed, 17 stored, tampered copy ignored, DB signals = pure pipeline per event; replay with a new group changes nothing |
| Mutation: SQL known-IP query counts all events | integration failed at `demo-a-…-06` (missing `new_ip_login`); file restored byte-identical |
| Operator run: `train` + `worker --idle-exit 15` on dev `security-events` | 17 processed; A: 37/37/37/37/67/87/90/89/89 (CRITICAL from the login), B: 18–23 LOW no signals, C: 60 HIGH alert then 32–35 |
| Leftover check after runs | 0 test DBs, 0 detect topics (stale sweep added for killed runs) |
| Gate scans | no secrets; model artifact ignored and unstaged; `apps/`, `contracts/` untouched; `security-events` still 17 |

## Decisions
D-046 (worker scope), D-047 (Python stack, delivery semantics, worker role), D-048 (rules), D-049 (features, Isolation Forest, artifact policy; resolves the open feature decision), D-050 (risk engine, alert threshold 40; resolves the open threshold decision), D-051 (psycopg IPv4/timeout).

## Known issues / limitations
- Risk score, anomaly score and `should_alert` are computed and logged but not persisted until Phase 05 (alerts table, D-046).
- Signals for the 17 dev events exist; Phase 05 must replay to create their alerts (new consumer group or `--group`), relying on idempotency.
- The model depends on the installed scikit-learn version (`load()` refuses a mismatch); retrain after upgrades. The artifact is never downloaded or committed (pickle).
- Scenario C's later events still sit at MEDIUM risk (32–35) from the suspicious IP plus context, below the alert threshold, by design.
- The worker is a single consumer process; no horizontal scaling or dead-letter topic (invalid messages are logged and skipped).
- The integration tests need Node and npm (Drizzle migrations are the only DDL source) and take about 50 s; `verify.py` now takes about 5 minutes.
- `pandas` (listed in the stack) is intentionally not used yet (D-047).

## Deferred work
None from Phase 04 scope.

## Next-agent requirements (Phase 05)
1. Verify this handoff and mark Phase 04 `COMPLETE` or `REJECTED`.
2. Record before coding: the correlation window and grouping keys (open decision), the incident lifecycle transitions, and alert idempotency (unique `alerts.event_id` already exists).
3. Persist alerts for `should_alert` results (risk, anomaly, `model_version`, severity, reasons) inside the same per-event transaction, then correlate into incidents (`incident_events`, `incident_alerts`).
4. Replay the dev topic once alerts exist and confirm scenario A → one incident (CRITICAL), C → one incident (HIGH/MEDIUM), B → none.
5. Keep detection deterministic on replay: correlation must also use event time and history strictly before the event.

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:migrate && npm run db:seed && npm run db:roles)
(cd services/detection && .venv/Scripts/python -m pip install -r requirements-dev.txt && .venv/Scripts/python -m sentinelx_detection.train)
python scripts/verify.py                      # expect: 23 checks: 0 failed
(cd services/detection && .venv/Scripts/python -m pytest -q)   # expect: 57 passed
```

## Rollback
`git revert <phase-04 commit>` restores Phase 03 (`b3d4ed9`). No schema changes in this phase. Dev data written by the worker can be removed with `TRUNCATE detection_signals, security_events CASCADE` as the owner, or by `docker compose down -v` and re-migrating. Reset the consumer group with a new `--group` or `DETECTION_GROUP_ID`.
