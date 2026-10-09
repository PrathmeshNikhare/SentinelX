# Phase 08 — LangGraph Investigation — Handoff

PHASE: 08
STATUS: READY_FOR_NEXT_PHASE
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `5623cb4` (Phase 07). Phase 08 is the commit that adds this file.
PREVIOUS PHASE: 07 accepted as COMPLETE at the start of this phase (db:roles ok, verify.py 23/23, ai pytest 122/122).

## Objective
Graph, state, bounded loops, trace persistence. Exit: a demo incident investigation completes asynchronously with a schema-valid verdict (Phase 06 schema) and an inspectable trace. Evidence-ID validation is Phase 10.

## Completed work
- **AI service** (`services/ai/sentinelx_ai/`):
  - `graph.py`: the docs/05 LangGraph, the `InvestigationState`, `ActionProposal` (action enum, no rationale), the deterministic fallback plan with `RULE_TECHNIQUES`, proposal validation, prompts, and `Investigator.run` for the background task (D-064, D-066).
  - Proposals are rejected and replaced by the fallback plan when the arguments are invalid, the tool is unavailable or the action repeats an earlier one. An unavailable LLM stops further proposals.
  - The 8-step budget bounds the loop. A traced proposal over 2,000 characters is stored by action name only.
  - Verdict: up to 2 attempts; the retry names the failed fields and never echoes the model output. Every attempt is kept in `raw_output_json`. When no attempt is valid, the run goes to review. When Ollama is down, the run is `failed` with evidence and trace kept (D-068).
  - `store.py`: persistence as `sentinelx_ai_writer`, refusing any other role. It queues runs under a per-incident advisory lock (unknown incident, or 409 when one is active), marks runs running and finishes them, loads incidents (20 newest events, 10 highest-risk alerts), appends trace and evidence, and marks unfinished runs failed at startup (D-065).
  - `evidence.py`: code-written claims, with log fields clipped and newlines collapsed (D-066). `log.py` was extracted from `app.py`.
  - `app.py`: `POST /v1/investigations` returns 202 and runs the graph in the background; 404/409/503 otherwise. `__main__.py` refuses to start unless the tools and writer roles check out, then abandons unfinished runs. `config.py` requires `AI_TOOLS_DATABASE_URL` and `AI_WRITER_DATABASE_URL`.
  - `tools.py`: `TOOL_INPUTS`, and `build_tools(db, None)` leaves out knowledge search until Phase 09 (D-067).
- **Web** (`apps/web/`, D-069):
  - `POST /api/incidents/:id/investigate`: checks the incident in the web database, calls the AI service through `src/server/ai-service.ts` (token, 5 s timeout, contract-checked 202), and returns 202/404/409/503.
  - `GET /api/investigations/:id`: run, trace and evidence, without the raw model output.
  - Incident page: Investigate button and latest-run status.
  - `src/contracts/investigation.ts` (zod) and `RUN_ID` in `src/lib/ids.ts`. The `notImplemented` helper is removed.
- **Roles:** `db:roles` also enables LOGIN for `sentinelx_ai_writer` from `AI_WRITER_DATABASE_URL`. `.env.example` gains the variable; the reference `.env` received it by append after a count-only check (never read). `db:roles` was run on the dev cluster.
- **Dependencies:** `langgraph` 1.2.14 (+ checkpoint 4.2.0, prebuilt 1.1.0, sdk 0.4.6, ormsgpack 1.12.2). `websockets` went from 17.2 to 16.1.1, as `langgraph-sdk` requires. 57 packages, no OSV advisories, `pip check` clean.
- **Dev database:** one demo run was created for `inc_646c689a3fff4bc3` (`run_e8ec29d8d0d54776`, completed, CRITICAL). It is useful for Phase 11.

## Files changed
Added:
- `services/ai/sentinelx_ai/{graph,store,evidence,log}.py`
- `services/ai/tests/test_graph.py`, `services/ai/tests/integration/{conftest,test_investigation_live}.py`
- `apps/web/src/contracts/investigation.ts`, `apps/web/src/server/{ai-service,ai-service.test}.ts`, `apps/web/src/server/queries/investigations.ts`
- `progress/handoffs/phase-08.md`

Modified:
- `services/ai/sentinelx_ai/{app,config,tools,__main__}.py`
- `services/ai/tests/{conftest,test_app,test_tools}.py`, `services/ai/tests/integration/{test_tools_db,test_ollama_live}.py`
- `services/ai/{README.md,requirements.txt}`
- `apps/web/src/app/api/incidents/[id]/investigate/route.ts`, `apps/web/src/app/api/investigations/[id]/route.ts`
- `apps/web/src/app/(console)/incidents/[id]/{page.tsx,actions.ts}`
- `apps/web/src/db/{admin,cli,env,db.db.test}.ts`, `apps/web/src/lib/ids.ts`, `apps/web/src/server/api.ts`
- `apps/web/e2e/{shell.spec,support}.ts`, `apps/web/playwright.config.ts`, `apps/web/README.md`
- `.env.example`, `README.md`
- `docs/{04_DATA_MODEL,05_AGENT_SPEC,06_TOOL_SPEC,14_API_CONTRACTS,16_ENVIRONMENT}.md`
- `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-07.md` (receiver acceptance)

No migration or schema change.

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 23 checks, 0 failed, 0 warnings |
| `services/ai` `pytest` | 148 passed (about 90 s with live Ollama) |
| `tests/test_graph.py` (18) | fallback-plan contents and window clamp; LLM proposals executed and the run completed (trace order, contiguous steps, evidence claims, verdict prompt); 4 invalid-proposal kinds plus oversized, duplicate and unparseable proposals fall back; step budget; Ollama down → full fallback plan, LLM asked once, run failed with evidence kept; invalid verdict ×2 → review with attempts kept; valid retry told what failed without echoing the output; tool failure traced; injected newlines cannot forge evidence lines; crash and missing incident → failed |
| `tests/test_app.py` | 202 with the background run called; 404/409/503 start nothing and leak no details; earlier auth, contract and size tests |
| `tests/integration/test_investigation_live.py` (3) | uvicorn + PostgreSQL + `llama3.2:3b`: 202 in under 5 s, 409 duplicate, `completed`, schema-valid verdict, no review, contiguous trace from `load_incident` to `validate_verdict`, 1–8 tool calls, trace evidence IDs exist, 9 event + 4 alert evidence rows; writer-role refusal; abandoned runs. Since the corrective-retry fix: 10 of 11 runs passed (49–78 s); the one failure was not captured (see known issues) |
| Live run on the dev database (`python -m sentinelx_ai`) | 202 in 0.11 s; completed in 61 s; "Possible account compromise", CRITICAL, T1110/T1078/T1059.001; 19 of 19 cited evidence IDs exist; 4 LLM-chosen actions, then 4 fallback actions after repeated duplicates |
| Web `npm test` / `test:db` / `test:e2e` | 94 / 39 / 18 passed. New: AI client (request shape, 404/409/401/503 mapping, contract violation, network timeout, misconfiguration, malformed IDs); E2E 404s for unknown targets, 503 with the AI service unreachable (API and button), a persisted run read back with trace and evidence, no raw output |
| Mutations (each restored byte-identical) | no step budget, no duplicate check, no availability check, no newline collapse, keep asking a down LLM, no writer role check: each fails a test |
| Gate scans | no test databases left (one left by a killed run after the machine slept was dropped); app/tools/writer roles LOGIN; `.env` untracked; temporary demo token deleted; port 8000 free |

## Decisions
D-064 (flow, graph, trace rows, langgraph pin), D-065 (writer role, run lifecycle, startup abandonment), D-066 (evidence claims, fallback plan, `RULE_TECHNIQUES`), D-067 (no knowledge search before Phase 09), D-068 (verdict attempts, review, the confidence finding), D-069 (web endpoints, AI client, incident page, E2E strategy).

## Known issues / limitations
- **Live-model flakiness.** One of 11 post-fix full live runs failed and the cause was not captured. The likely cause is model nondeterminism (D-056): a verdict sent to review, or the single-attempt Phase 06 adapter test. When the model misbehaves, the system responds correctly (review or failed run), and that is unit-tested. The live assertions intentionally test model quality.
- **Ollama does not enforce numeric bounds** (`confidence` 93 was observed). This is mitigated by the prompt and the corrective retry (D-068), not eliminated.
- **No grounding yet (Phase 10).** A schema-valid verdict may cite missing evidence IDs or misstate facts. The dev-run summary said 4 failed logins where the evidence shows 5. Severity disagreement (D-016) is also not checked yet.
- **The 3B model tends to repeat actions after about 4 steps.** The fallback plan fills the budget, so some fallback evidence overlaps the LLM's own (a different history window).
- **The web GET returns evidence `data` in full** (bounded by the tools at 32 KiB per row). Phase 11 decides what to render.
- **Startup abandonment assumes one AI service instance** (`ponytail:` in `store.py`).
- **TestClient runs background tasks before returning.** Asynchrony is therefore proven only by the uvicorn-based live test and the live dev run.
- **The browser cannot fetch `raw_output_json`.** Review tooling arrives with Phase 10/11.

## Deferred work
None from Phase 08 scope. Evidence-ID and MITRE-ID validation, the severity-disagreement rule and the hardened prompt are Phase 10. The trace, verdict and evidence UI is Phase 11. Knowledge retrieval is Phase 09.

## Next-agent requirements (Phase 09)
1. Verify this handoff and mark Phase 08 `COMPLETE` or `REJECTED`.
2. Resolve the open decision on the embedding model and vector dimension before building. Pin `qdrant-client` and `sentence-transformers` (CPU torch), skipping day-old releases.
3. Implement `KnowledgeRetriever` over Qdrant, honoring `timeout_seconds` and raising `TimeoutError`/`ConnectionError` (D-063). Ingest approved documents into `knowledge_documents` (owner role) with `kd_` IDs that hits carry.
4. Pass the retriever to `build_tools(...)` in `create_app`. `search_security_knowledge` then appears in `available_tools`; consider adding it to the fallback plan (D-066).
5. Retrieval smoke tests must assert source IDs (Phase 09 exit).

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:roles)             # needs AI_TOOLS_/AI_WRITER_DATABASE_URL in .env (from .env.example)
(cd services/ai && .venv/Scripts/python -m pip install -r requirements-dev.txt)
python scripts/verify.py                      # expect: 23 checks: 0 failed (needs Ollama with OLLAMA_MODEL)
(cd services/ai && .venv/Scripts/python -m pytest -q)   # expect: 148 passed; keep the machine awake (about 90 s)
(cd services/ai && .venv/Scripts/python -m pytest -q -s tests/integration/test_investigation_live.py)  # prints the demo verdict and steps
```

## Rollback
- Code: `git revert <phase-08 commit>` restores Phase 07 (`5623cb4`). No schema change.
- Roles: `ALTER ROLE sentinelx_ai_writer NOLOGIN;` undoes the writer login.
- Dev data: the dev database holds one investigation run with its trace and evidence. These are append-only and no role can delete them; remove them as the owner if desired.
- Dependencies: reinstall the AI venv from the reverted `requirements-dev.txt` to drop langgraph, and restore `websockets` 17.2.
