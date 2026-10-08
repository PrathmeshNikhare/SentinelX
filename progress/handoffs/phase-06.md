# Phase 06 — AI Service Foundation — Handoff

PHASE: 06
STATUS: COMPLETE (receiver accepted 2026-10-09 at Phase 07 start: verify.py 23/23, ai pytest 58/58, auth middleware and adapter inspected)
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `7dd87e6` (Phase 05). Phase 06 is the commit that adds this file.
PREVIOUS PHASE: 05 accepted as COMPLETE at the start of this phase (verify.py 23/23, detection pytest 72/72).

## Objective
FastAPI, health endpoint, internal auth (`AI_SERVICE_TOKEN`), contracts, Ollama adapter, verdict Pydantic schema. Exit: model adapter configurable; schema-invalid output rejected; unauthenticated calls rejected.

## Completed work
- `services/ai/sentinelx_ai/`:
  - `config` (D-025 refusal, timeout bounds);
  - `contracts` (Verdict, InvestigationRequest, InvestigationAccepted; generator plus `contracts/v1/*.schema.json` and examples, D-059);
  - `llm` (`OllamaClient`: JSON-Schema `format`, temperature 0, seed 42, Pydantic re-validation, `LlmUnavailable` vs `LlmInvalidOutput` with bounded raw output kept for audit, messages never echo model output, D-056);
  - `app` (auth middleware before routing and parsing, constant-time token compare, docs disabled, `/health`, `/v1/ready`, `POST /v1/investigations` contract-validated then 501 until Phase 08, 16 KiB body cap, D-057/D-058);
  - `__main__` (binds 127.0.0.1).
- Dependencies pinned and frozen in `requirements.txt` (OSV: no advisories); `colorama` included with a Windows marker for `click`.
- `.env.example` gains `AI_SERVICE_TOKEN=` (empty, so the service refuses to start). The reference `.env` received a generated token by append (never read or printed).
- `scripts/verify.py`: an unreachable Ollama is now FAIL (was WARN until Phase 06).
- Live findings recorded in D-056:
  - `temperature 0` plus a seed is near-deterministic only: with the full schema, two calls differed in one MITRE ID;
  - the 3B model invents plausible-looking MITRE IDs (`T1003`, `T1210`, `T1210.001`), which motivates Phase 10's existence validation;
  - cold start took 40.5 s, warm calls about 5–7 s.

## Files changed
Added: `services/ai/sentinelx_ai/{config,contracts,llm,app,__main__}.py`, `services/ai/tests/{conftest,test_app,test_contracts_and_config,test_llm}.py`, `services/ai/tests/integration/{__init__,test_ollama_live}.py`, `contracts/v1/{verdict,investigation-request,investigation-accepted}.schema.json`, `contracts/v1/examples/{verdict,investigation-request,investigation-accepted}.json`, `progress/handoffs/phase-06.md`.
Modified: `.env.example`, `README.md`, `contracts/v1/README.md`, `docs/{14_API_CONTRACTS,16_ENVIRONMENT}.md`, `scripts/verify.py`, `services/ai/{README.md,pyproject.toml,requirements.txt}`, `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-05.md` (receiver acceptance).

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 23 checks, 0 failed (Ollama now required) |
| `services/ai` `pytest` | 58 passed in about 8 s: contract drift and examples; 14 verdict rejection cases (extra field, confidence 1.5/NaN, bad severity, short verdict, empty summary, empty/malformed/duplicate evidence IDs, malformed/duplicate MITRE IDs, recommendation count/length); request ID/extra-field rejection; 5 unsafe tokens refused; settings parsing; adapter request shape (format = schema, options, messages); schema-invalid/non-JSON/incomplete/malformed-envelope output → `LlmInvalidOutput` with raw kept and never echoed; timeout/refused/404/500 → `LlmUnavailable`; tag-list availability; raw bounded to 20 KB; app 401 on 3 routes × 4 bad headers, docs disabled, ready 200/503, contract 400 without value echo, 501 phase 08, 413, error shape; live `llama3.2:3b` returns a schema-valid verdict citing only supplied evidence |
| Mutation: disable the token check | 12 of 20 app tests failed; restored byte-identical |
| Live service (`python -m sentinelx_ai`) | `/health` 200; `/v1/ready` and `/docs` 401 without token; ready 200 `llama3.2:3b` with token; investigations 501 / invalid 400; listens on 127.0.0.1:8000 only |
| Placeholder token startup | `AI_SERVICE_TOKEN=replace-me` → `ai.config_invalid`, exit 1, no listener |
| Gate scans | contracts regenerate identically; no real tokens tracked; web and detection untouched |

## Decisions
D-056 (model, structured output, timeout, non-determinism and hallucination findings; resolves the open decision), D-057 (service structure, httpx adapter), D-058 (internal auth, docs disabled), D-059 (AI-owned Pydantic contracts).

## Known issues / limitations
- Ollama output is not guaranteed reproducible even at temperature 0 (D-056). Tests assert schema validity, not exact text.
- The live model cites MITRE IDs that do not exist in the curated set. Nothing rejects them until Phase 10 (expected).
- The FastAPI body cap checks `Content-Length` only (`ponytail:` note); the only caller, the Next.js server, always sends it.
- Starlette prints a deprecation warning that its test client wants `httpx2`; tests are unaffected and no dependency was added.
- The AI database roles are still NOLOGIN: Phase 06 does not touch PostgreSQL. Phases 07–08 enable them (D-031).
- The CLAUDE.md verdict illustration uses `ev_1`-style IDs; real IDs are `ev_<16 hex>` (D-030), which the contract enforces.

## Deferred work
None from Phase 06 scope.

## Next-agent requirements (Phase 07)
1. Verify this handoff and mark Phase 06 `COMPLETE` or `REJECTED`.
2. Phase 07 brings in LangChain for typed tools (stack). Pin `langchain-core` and record why; keep the adapter in `llm.py` as the only LLM path.
3. Enable LOGIN for `sentinelx_ai_tools` (SELECT-only) via an owner command, as `db:roles` does for the app role (D-031). The tools must connect only as that role and use fixed parameterized queries with bounds (docs/06).
4. `search_security_knowledge` uses a retriever interface with a fake in Phase 07; Qdrant comes in Phase 09 (D-026).

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd services/ai && .venv/Scripts/python -m pip install -r requirements-dev.txt)
python scripts/verify.py                      # expect: 23 checks: 0 failed (needs Ollama with OLLAMA_MODEL)
(cd services/ai && .venv/Scripts/python -m pytest -q)   # expect: 58 passed
(cd services/ai && .venv/Scripts/python -m sentinelx_ai) # needs AI_SERVICE_TOKEN in .env; serves 127.0.0.1:8000
```

## Rollback
`git revert <phase-06 commit>` restores Phase 05 (`7dd87e6`). No database changes. Remove `AI_SERVICE_TOKEN` from `.env` if desired. The AI service process is stopped with Ctrl+C.
