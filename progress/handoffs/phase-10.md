# Phase 10 — Evidence-Grounded Verdict — Handoff

PHASE: 10
STATUS: COMPLETE (receiver accepted 2026-10-09 at Phase 11 start: db:roles ok, verify.py 24/24 incl. the live grounded investigation)
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `e6b23cf` (Phase 09). Phase 10 is the commit that adds this file.
PREVIOUS PHASE: 09 accepted as COMPLETE at the start of this phase (ai pytest 173/173, verify.py 24/24, run under low memory).

## Objective
Hardened prompt, evidence-ID and MITRE-ID validation, the severity-disagreement rule (D-016), the review path and raw-output audit storage (D-019). Exit: supported claims cite evidence; unsupported references force review.

## Completed work
- `services/ai/sentinelx_ai/grounding.py` (D-073): `check_verdict` returns findings, each with an effect:
  - **reject**: an unknown evidence ID; a MITRE ID outside the curated set; a curated MITRE ID that was not retrieved in the run; any unresolved `ev_…`/`T####` written into the summary or recommendations;
  - **note**: severity one level from the deterministic incident severity;
  - **review**: severity two or more levels away.
  Findings name IDs and paths only.
- `graph.py`:
  - prompt `investigation-v2` (fenced evidence, the supported-techniques list, hedging, approval framing);
  - evidence state marks `technique` support (found MITRE lookups and `mitre-attack` knowledge hits);
  - `build_verdict` validates each schema-valid answer and retries once, naming what failed; every attempt is kept with its output and findings;
  - `validate_verdict` writes `validation_errors` as `{attempt, code, detail, effect}` and sets `requires_review` when nothing was accepted or a finding is `review`;
  - `Deps.tool_db` provides the curated-set lookup.
- `tools.py`: `known_techniques()` with the fixed `KNOWN_TECHNIQUES_SQL` (tools role; not an agent tool). `store.py`: structured validation errors. `app.py`: passes `tool_db`.
- No dependency, schema, migration or web change; the web API passes the new `validationErrors` shape through.

## Files changed
Added:
- `services/ai/sentinelx_ai/grounding.py`
- `services/ai/tests/test_grounding.py`, `services/ai/tests/integration/test_review_path_db.py`
- `progress/handoffs/phase-10.md`

Modified:
- `services/ai/sentinelx_ai/{graph,tools,store,app}.py`
- `services/ai/tests/{test_graph,test_tools}.py`, `services/ai/tests/integration/test_investigation_live.py`
- `services/ai/README.md`
- `docs/{04_DATA_MODEL,05_AGENT_SPEC,14_API_CONTRACTS,15_PROMPT_POLICY}.md`
- `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-09.md` (receiver acceptance)

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 24 checks, 0 failed, 0 warnings |
| `services/ai` `pytest` | 194 collected, all passing |
| `tests/test_grounding.py` (9) | support sources (playbook hits excluded); grounded verdict has no findings; invented evidence ID; unknown vs unretrieved MITRE ID; IDs inside summary and recommendations; severity gap 0/1/2/3 in both directions → none/note/review/review, never reject; feedback names references only |
| `tests/test_graph.py` additions (7) | invented evidence ID retried with the ID named, then accepted, with the rejected attempt kept; ungrounded twice → rejected, verdict null, both outputs kept, findings per attempt, trace `accepted=false`; LOW vs CRITICAL keeps the verdict and forces review; MITRE `T1110` retrieved → accepted, `T1005` curated but not retrieved → rejected, `T9999` → rejected; prompt lists supported techniques; injected `END EVIDENCE` cannot close the fence; "none" when nothing was retrieved |
| `tests/integration/test_review_path_db.py` | real Store and tools roles in PostgreSQL: an ungrounded verdict ends `completed`, `requires_review`, `verdict_json` null, both attempts kept; findings include `unknown_mitre_technique` for `T1003` against the real curated table |
| `tests/integration/test_investigation_live.py` (3 runs) | accepted on the first attempt with no findings each time; 15–20 cited IDs, all this run's evidence; MITRE ⊆ supported (`T1110`, `T1078`); 57–77 s. Grounding is now asserted, not just printed |
| Mutations (each restored byte-identical) | no evidence-ID check, no MITRE support check, no MITRE existence check, no inline reference check, severity threshold 3, accept rejected verdicts, ignore review findings: each fails a test |
| Probe: database down during validation | run `failed`, `requires_review`, no verdict accepted (fails closed) |
| Gate scans | no test databases or collections left; worktree contains only Phase 10 changes |

## Decisions
D-073 (grounding rules, retry with named references, storage shapes, prompt v2, live results, limitation).

## Known issues / limitations
- **The checks prove references, not sentences.** A cited ID is real and retrieved, but the sentence it is attached to may still be wrong (an earlier run miscounted failed logins). Claim-level verification is out of scope; the evidence panels (Phase 11) and the review flag are the human check.
- **A database outage during validation crashes the run** (fails closed: `failed`, `requires_review`). That attempt's model output is not stored because the crash handler records no attempts, a small gap against "every output kept" (D-019).
- **Playbook hits do not support MITRE IDs** even though they list related techniques. This is conservative by design; the agent must look the technique up or retrieve its MITRE document.
- **Three live runs is a small sample.** The 3B model's grounding was clean, but the review path will trigger on some runs; that is the intended behavior.
- **Memory on the reference machine was very low** (0.3–0.8 GB available) during this phase. All gates passed regardless, but the background services were stopped by Claude Code's memory reaper earlier and were not restarted.

## Deferred work
None from Phase 10 scope.

## Next-agent requirements (Phase 11)
1. Verify this handoff and mark Phase 10 `COMPLETE` or `REJECTED`.
2. Build the incident investigation UI from `GET /api/investigations/:id` (docs/09):
   - timeline, signals, evidence panels (claim, source type, source ID, data);
   - MITRE references with sources;
   - the trace (step, action, origin `llm`/`fallback`, tool, reason);
   - the verdict, labelled "AI-assessed severity" and "model-reported, uncalibrated confidence" (D-016), with the deterministic risk shown separately;
   - recommendations;
   - a prominent review banner listing `validationErrors` (`code`, `detail`, `effect`).
3. Poll a queued or running run; render the failed and review states.
4. Keep `raw_output_json` server-side unless a reviewer view is designed deliberately.

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:roles)
(cd services/ai && .venv/Scripts/python -m sentinelx_ai.knowledge)   # idempotent
python scripts/verify.py                      # expect: 24 checks: 0 failed
(cd services/ai && .venv/Scripts/python -m pytest -q)   # expect: 194 passed (live Ollama, Qdrant, model)
(cd services/ai && .venv/Scripts/python -m pytest -q -s tests/integration/test_investigation_live.py)  # prints the grounded verdict
```

## Rollback
`git revert <phase-10 commit>` restores Phase 09 (`e6b23cf`). There are no schema, data or dependency changes. Runs created under Phase 10 keep the richer `raw_output_json` and `validation_errors_json` shapes; both columns are untyped jsonb.
