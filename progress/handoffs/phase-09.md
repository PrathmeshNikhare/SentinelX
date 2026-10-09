# Phase 09 — RAG / MITRE — Handoff

PHASE: 09
STATUS: COMPLETE (receiver accepted 2026-10-09 at Phase 10 start: ai pytest 173/173, verify.py 24/24, under low memory)
GATE: `/verify-phase` APPROVED (2026-10-09)
BASE COMMIT: `9832e2c` (Phase 08). Phase 09 is the commit that adds this file.
PREVIOUS PHASE: 08 accepted as COMPLETE at the start of this phase (db:roles ok, verify.py 23/23 incl. the live investigation test).

## Objective
Document ingestion, embeddings, Qdrant, MITRE retrieval and source references. Exit: retrieval smoke tests with source IDs.

## Completed work
- `fixtures/knowledge/playbooks.json`: 8 short defensive playbooks written for SentinelX. Each lists related techniques from the curated set; no external text was copied.
- `services/ai/sentinelx_ai/knowledge.py` (D-070–D-072):
  - corpus: MITRE documents built from `fixtures/mitre_techniques.json`, plus the playbooks; one document = one retrieval unit, under 1,500 characters;
  - `SentenceEmbedder`: `all-MiniLM-L6-v2` at Hub commit `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, normalized, CPU, loaded lazily;
  - `qdrant_client()`: IPv4 for `localhost`, version check off;
  - `QdrantRetriever`: lazy client; `TimeoutError`/`ConnectionError` contract; payloads validated into `KnowledgeHit`;
  - `ingest()` plus the CLI `python -m sentinelx_ai.knowledge` (owner role): upsert rows and points, remove documents no longer in the corpus, recreate the collection on a dimension change.
- `tools.py`: `KnowledgeHit.external_id`, and a fixed `KNOWLEDGE_DOCUMENTS_SQL` (tools role) that drops hits whose document is not stored.
- `graph.py`: the fallback plan adds a top-3 knowledge search for the incident title plus the detected rule names. `evidence.py`: the knowledge claim includes source and external ID.
- `config.py`: `qdrant_url` and `knowledge_collection` (`QDRANT_URL`, `KNOWLEDGE_COLLECTION`), plus a shared `pg_connect_options()` now used by `tools.py`, `store.py` and `knowledge.py` (removes duplicated connect code).
- `app.py`: `default_retriever(settings)`; knowledge search is offered at runtime. `__main__.py` warms the embedding model in a background thread (`ai.embedding_model` log).
- `scripts/verify.py`: 24th check, the knowledge collection holds exactly the corpus' document count.
- Dependencies: `qdrant-client` 1.15.1 (matches server 1.15.0), `sentence-transformers` 6.1.0, `torch` 2.14.1 (CPU), `transformers` 5.18.0 and their transitives. 85 pins plus 3 Windows markers (`pywin32` added); 94 venv packages, no OSV advisories, `pip check` clean.
- Dev environment:
  - the corpus is ingested into the dev database (19 `knowledge_documents`) and Qdrant `security_knowledge` (19 points);
  - the model is cached in `~/.cache/huggingface`;
  - the AI service I run in the background was restarted on Phase 09 code (healthy, model warmed).

## Files changed
Added:
- `fixtures/knowledge/playbooks.json`
- `services/ai/sentinelx_ai/knowledge.py`
- `services/ai/tests/test_knowledge.py`, `services/ai/tests/integration/test_knowledge_live.py`
- `progress/handoffs/phase-09.md`

Modified:
- `services/ai/sentinelx_ai/{__main__,app,config,evidence,graph,store,tools}.py`
- `services/ai/tests/{test_graph,test_tools}.py`, `services/ai/tests/integration/{conftest,test_investigation_live}.py`
- `services/ai/{README.md,requirements.txt}`
- `scripts/{verify.py,README.md}`
- `README.md`, `fixtures/README.md`
- `docs/{05_AGENT_SPEC,06_TOOL_SPEC,16_ENVIRONMENT}.md`
- `progress/{DECISIONS,STATUS,PHASE_LOG,CURRENT_HANDOFF}.md`, `progress/handoffs/phase-08.md` (receiver acceptance)

No migration or schema change (`knowledge_documents` existed since Phase 01).

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` | 24 checks, 0 failed, 0 warnings |
| `services/ai` `pytest` | 173 collected, all passing |
| `tests/test_knowledge.py` (14) | corpus = curated MITRE set + 8 playbooks; unique, stable point IDs; sizes; playbook techniques curated; content hash; oversized/duplicate documents rejected; in-memory Qdrant with a hashing embedder (source references best first; invalid payloads never returned; wrong-size collection recreated); timeout/refused/404 → `TimeoutError`/`ConnectionError`; missing model → unavailable; lazy client; `localhost` → 127.0.0.1; warm-up |
| `tests/test_tools.py` additions | hits keep `external_id`; hits whose document is not stored are dropped; fourth fixed SELECT in the capability scan |
| `tests/test_graph.py` addition | the fallback plan searches knowledge for the detected rules when the tool is offered |
| `tests/integration/test_knowledge_live.py` (9, about 46 s) | one row and one point per document, payload `document_id` = row ID; **5 smoke queries return an expected source ID in their top 3, every hit matching a stored row**; agent tool as the tools role; re-ingest idempotent and removes a retired document's row and point; closed port or missing collection → `ToolError` `unavailable` |
| `tests/integration/test_investigation_live.py` | with the real retriever: completed, CRITICAL, 3 knowledge evidence rows, 20 of 20 cited IDs exist (64 s) |
| Mutations (each restored byte-identical) | no stored-document check, invalid points not dropped, no IPv4 mapping, timeouts not distinguished: each fails a test |
| Live `python -m sentinelx_ai` | `/health` 200 immediately; `ai.embedding_model loaded=true` about 40 s later |
| Gate scans | no `sentinelx_*` test databases; Qdrant holds only `security_knowledge`; `.env` untracked |

## Decisions
D-070 (embedding model and RAG pins, model download and warm-up, IPv4 for Qdrant, lazy client), D-071 (corpus, ingestion CLI, stable IDs, sync, `verify.py` check), D-072 (retriever contract, `external_id`, stored-document check, fallback-plan knowledge search, evidence). The open embedding decision is resolved.

## Known issues / limitations
- **First model load needs network.** The first ingestion or start downloads the model from Hugging Face (about 90 MB). Offline machines need a pre-populated cache.
- **A cold model load takes 19–40 s** (torch import). The service is usable meanwhile, but a knowledge search during that window waits for the load: the 5 s tool timeout covers only the Qdrant call.
- **Linux installs** from `requirements.txt` would pull CUDA torch from PyPI. Phase 13's image must use the PyTorch CPU index (noted in `requirements.txt`).
- **Local Qdrant has no API key**; it listens on 127.0.0.1 only. Phase 12 hardening.
- **The playbooks are short and project-written**, so retrieval quality is demo-grade (19 documents). The smoke queries assert an expected source in the top 3, not rank 1.
- **The verdict still isn't validated against evidence or MITRE IDs.** Grounding, MITRE-ID existence and the severity rule are Phase 10.
- **The web console on port 3000** is still the earlier dev server without `AI_SERVICE_TOKEN`; I was not permitted to stop it. Use the production build on 3005, which I started earlier in the session.

## Deferred work
None from Phase 09 scope.

## Next-agent requirements (Phase 10)
1. Verify this handoff and mark Phase 09 `COMPLETE` or `REJECTED`.
2. Harden the verdict prompt (docs/15) and validate after `build_verdict`:
   - every `evidence_ids` entry must exist for the run;
   - every `mitre_techniques` entry must be in `mitre_techniques`, or cited through `mitre` or `knowledge` evidence;
   - the severity-disagreement rule of two or more levels sets `requires_review` (D-016).
   On failure, reject the verdict: `verdict_json` null, `requires_review=true`, raw output kept (D-019).
3. `validate_verdict` currently records `deferred_to_phase_10`; replace that with the real checks, and keep validation errors free of model output (field paths and IDs only).
4. Consider retrying once with the failed checks named, as the schema retry does (D-068).

## Verification commands
```sh
git status                                    # clean
docker compose up -d
(cd apps/web && npm run db:roles)
(cd services/ai && .venv/Scripts/python -m pip install -r requirements-dev.txt)
(cd services/ai && .venv/Scripts/python -m sentinelx_ai.knowledge)   # expect knowledge.ingest documents=19
python scripts/verify.py                      # expect: 24 checks: 0 failed
(cd services/ai && .venv/Scripts/python -m pytest -q)   # expect: 173 passed (live Ollama, Qdrant, model; about 3 min)
```

## Rollback
- Code: `git revert <phase-09 commit>` restores Phase 08 (`9832e2c`). No schema change.
- Data: remove the corpus with `DELETE FROM knowledge_documents;` (owner role) and `curl -X DELETE http://127.0.0.1:6333/collections/security_knowledge`. The Hugging Face cache may stay.
- Dependencies: reinstall the AI venv from the reverted `requirements-dev.txt` to drop torch, sentence-transformers and qdrant-client.
