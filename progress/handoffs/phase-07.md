# Phase 07 — Agent Tools — Handoff

PHASE: 07
STATUS: READY_FOR_NEXT_PHASE
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `cd4436c` (Phase 06). Phase 07 is the commit that adds this file.
PREVIOUS PHASE: 06 accepted as COMPLETE at the start of this phase (verify.py 23/23, ai pytest 58/58, auth middleware and adapter inspected).

## Objective
Five typed read-only tools, bounds and tests; `search_security_knowledge` against a retriever interface tested with a fake (D-026). Exit: no arbitrary SQL/shell/network mutation; tools run under the SELECT-only role.

## Completed work
- `services/ai/sentinelx_ai/tools.py`:
  - five LangChain `StructuredTool`s: `get_user_history`, `get_ip_reputation`, `get_related_logs`, `get_mitre_technique`, `search_security_knowledge`;
  - Pydantic input schemas (extra fields forbidden) and typed output schemas;
  - `metadata = {read_only, timeout_seconds, max_result_bytes}` (D-060);
  - bounds (D-062): window ≤ 7 days, limit 1–50, `top_k` 1–10, results ≤ 32 KiB with `truncated`;
  - `connect_tools()`: refuses any role but `sentinelx_ai_tools`; read-only session, 2 s statement timeout, UTC, IPv4 for localhost (D-061);
  - three constant `SELECT` queries;
  - `ToolError(tool, code)` with codes timeout/unavailable/oversized and no SQL or data in the message;
  - the `KnowledgeRetriever` protocol (D-063).
- `config.refuse_cloud_tracing()`: the service refuses to start when LangSmith tracing variables are `true` (D-060).
- `npm run db:roles` now also enables LOGIN for `sentinelx_ai_tools` from `AI_TOOLS_DATABASE_URL` (`enableRoleLogin`; `enableAppRoleLogin` is kept for the E2E prep). `sentinelx_ai_writer` stays NOLOGIN.
- `AI_TOOLS_DATABASE_URL` was added to `.env.example`. The reference `.env` received the same line by append, after a count-only check that it was absent (never read or printed). `db:roles` was run on the dev cluster.
- Dependencies: `langchain-core` 1.6.7 and `psycopg[binary]` 3.3.6, transitives frozen in `requirements.txt`. 52 packages, no OSV advisories, `pip check` clean.

## Files changed
Added: `services/ai/sentinelx_ai/tools.py`, `services/ai/tests/test_tools.py`, `services/ai/tests/integration/test_tools_db.py`, `progress/handoffs/phase-07.md`.
Modified: `.env.example`, `apps/web/src/db/{admin,cli,env,db.db.test}.ts`, `apps/web/README.md`, `services/ai/sentinelx_ai/config.py`, `services/ai/{README.md,requirements.txt}`, `docs/{04_DATA_MODEL,06_TOOL_SPEC,16_ENVIRONMENT}.md`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-06.md` (receiver acceptance). No migration or schema change.

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 23 checks, 0 failed, 0 warnings (web unit/db/kafka/e2e, detection, ai) |
| `services/ai` `pytest` | 122 passed in about 30 s (58 from Phase 06 plus 64 new) |
| `tests/test_tools.py` (47) | registry is exactly 5 read-only tools with closed schemas; out-of-bounds input rejected (SQL injection in `user_id`, uppercase, limit 0/51, empty or over-7-day window, naive timestamps, unknown fields, untargeted related logs, bad/CIDR/injected IPs, duplicate or unknown event types, malformed technique IDs, query length, control characters, `top_k`); invalid args never reach the DB; parameters, `limit+1` truncation and UTC conversion; 32 KiB byte budget with 4 KB metadata rows; typed not-found results; retriever timeout pass-through, cap and error mapping; `kd_` IDs and finite scores enforced; psycopg errors mapped without details; AST scan (allowed imports only, no eval/exec/open, constant SELECT queries only); tracing refusal |
| `tests/integration/test_tools_db.py` (17) | throwaway DB migrated, seeded and roles enabled through npm; owner and app URLs refused by `connect_tools`; session read-only (`ReadOnlySqlTransaction`) with 2000 ms timeout; in an explicit `READ WRITE` transaction INSERT/UPDATE/DELETE/TRUNCATE, evidence INSERT, analysts/analyst_sessions/investigation_runs SELECT and CREATE TABLE all raise `InsufficientPrivilege`; `pg_sleep(3)` raises `ToolError` timeout; every tool returns the expected rows (user and window scoping, newest first, truncation, IP filter, event-type filter, seeded reputation, curated MITRE); injected text in `resource`/`metadata` is returned verbatim and the row count is unchanged |
| Mutations (each restored byte-identical) | dropping the role check, the read-only session, the extra row, the byte budget or the `top_k` cap: each fails at least one test |
| `LANGSMITH_TRACING=true python -m sentinelx_ai` | `ai.config_invalid`, exit 1 |
| Gate scans | no `sentinelx_*` test databases left; roles: app and tools LOGIN, writer NOLOGIN; `.env` untracked |

## Decisions
D-060 (LangChain `StructuredTool`, pins, LangSmith tracing refusal), D-061 (tools-only role connection, read-only sessions, `db:roles`), D-062 (tool bounds, errors, fixed queries), D-063 (knowledge retriever interface).

## Known issues / limitations
- Tool results include attacker-controllable log text (`resource`, `metadata`). The tools return it as data. Keeping it from steering the model is prompt and verdict hardening (Phases 08/10, docs/15).
- `ToolDatabase.fetch` accepts any query string from Python callers. Only the tools call it and the LLM never reaches it; grants, the read-only session and the timeout still apply. Phase 08 must not expose it.
- One connection per tool call (a few ms locally). A pool is unnecessary at investigation scale.
- `get_related_logs` requires `user_id` or `source_ip`, which is stricter than docs/06's "optional": an unscoped scan has no investigative use (D-062).
- The `.env.example` role passwords are local placeholders like `sentinelx_app_local`. Nothing refuses them (they are local-only, as in Phase 02).
- Starlette's `httpx2` deprecation warning from Phase 06 remains. `httpx2` is now installed (a langsmith dependency), but the test client still uses `httpx`; harmless.

## Deferred work
None from Phase 07 scope. The Qdrant retriever implementation is Phase 09 (D-026).

## Next-agent requirements (Phase 08)
1. Verify this handoff and mark Phase 07 `COMPLETE` or `REJECTED`.
2. Pin `langgraph` (1.2.x requires `langchain-core>=1.4.7`; 1.6.7 is installed) and skip day-old releases.
3. Enable LOGIN for `sentinelx_ai_writer` the same way (`db:roles` + a URL variable). Persist runs, trace and evidence as that role only. Update the db test that asserts the writer is NOLOGIN.
4. Build the graph on `build_tools(ToolDatabase(AI_TOOLS_DATABASE_URL), retriever)`. Validate LLM action proposals with the tool's `args_schema` (D-017). Catch `ToolError` and `ValidationError` per step and continue or fall back. Store each tool result as an evidence row (D-018).
5. Phase 08 needs a retriever before Qdrant exists (Phase 09): use an empty or fixture-backed `KnowledgeRetriever` and record the choice.
6. Add `AI_TOOLS_DATABASE_URL` to `Settings` when the service starts using the tools.

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:roles)             # needs AI_TOOLS_DATABASE_URL in .env (copy from .env.example)
(cd services/ai && .venv/Scripts/python -m pip install -r requirements-dev.txt)
python scripts/verify.py                      # expect: 23 checks: 0 failed
(cd services/ai && .venv/Scripts/python -m pytest -q)   # expect: 122 passed (needs PostgreSQL, npm, Ollama)
```

## Rollback
`git revert <phase-07 commit>` restores Phase 06 (`cd4436c`). No schema change. `ALTER ROLE sentinelx_ai_tools NOLOGIN;` undoes the login. The `AI_TOOLS_DATABASE_URL` line in `.env` may stay or be removed. Reinstall the AI venv from the reverted `requirements-dev.txt` to drop `langchain-core`/`psycopg`.
