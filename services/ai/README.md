# services/ai

Owner: AI Agent Engineer (docs/19_AGENT_OWNERSHIP.md)

FastAPI AI service (D-057). Internal only: it binds `127.0.0.1:8000`, and every route except `/health` requires `Authorization: Bearer <AI_SERVICE_TOKEN>` (D-058). Phase 06 provides the foundation: settings, contracts, the Ollama adapter and the HTTP surface. Tools (07), the LangGraph investigation (08), RAG (09) and verdict validation (10) build on it.

## Modules (`sentinelx_ai/`)
| Module | Role |
|---|---|
| `config.py` | settings from the repo-root `.env`; refuses unsafe tokens and bad timeouts (D-025) |
| `contracts.py` | Pydantic source of `contracts/v1/{verdict,investigation-request,investigation-accepted}.schema.json` (D-059) |
| `llm.py` | `LlmClient` protocol + `OllamaClient`: schema-constrained `/api/chat`, temperature 0, seed 42, Pydantic re-validation, typed errors (`LlmUnavailable` vs `LlmInvalidOutput`, with the raw output kept for audit) (D-056) |
| `app.py` | `create_app()`: auth middleware before routing, JSON error shape, `GET /health`, `GET /v1/ready`, `POST /v1/investigations` (202 and a background run; 404/409/503, D-064) |
| `graph.py` | LangGraph investigation: state, nodes, LLM action proposals validated against tool schemas with a deterministic fallback plan, 8-step budget, verdict attempts, `Investigator.run` for the background task (D-064, D-066–D-068) |
| `store.py` | persistence as `sentinelx_ai_writer`: queue/start/finish runs, load incidents, append trace and evidence, abandon unfinished runs at startup (D-065) |
| `grounding.py` | evidence-grounded verdict checks: cited evidence IDs, curated and retrieved MITRE IDs, IDs in prose, severity disagreement (D-073) |
| `evidence.py` | code-written evidence claims for incident rows and tool results (D-066) |
| `log.py` | JSON log lines |
| `knowledge.py` | knowledge corpus (MITRE techniques + playbooks), `SentenceEmbedder` (all-MiniLM-L6-v2, pinned), `QdrantRetriever`, owner-role ingestion CLI `python -m sentinelx_ai.knowledge` (D-070–D-072) |
| `tools.py` | the five read-only agent tools as LangChain `StructuredTool`s: Pydantic input/output schemas, bounds, `sentinelx_ai_tools`-only read-only sessions, fixed `SELECT`s, the `KnowledgeRetriever` interface (D-060–D-063) |
| `__main__.py` | `python -m sentinelx_ai` |

## Setup and run
Python 3.12 (D-024).

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m sentinelx_ai.knowledge       # ingest the knowledge corpus (owner role; once, idempotent)
.venv\Scripts\python -m sentinelx_ai                 # 127.0.0.1:8000 (AI_SERVICE_PORT overrides)
```

Environment (repo-root `.env`):
- `AI_SERVICE_TOKEN`: required; random, 32+ characters;
- `OLLAMA_BASE_URL` (default `http://localhost:11434`);
- `OLLAMA_MODEL` (`llama3.2:3b`, pulled with `ollama pull llama3.2:3b`);
- optional `OLLAMA_TIMEOUT_SECONDS` (default 120);
- `AI_TOOLS_DATABASE_URL`: the SELECT-only tools role, enabled by `npm run db:roles` in `apps/web` (D-061);
- `AI_WRITER_DATABASE_URL`: the investigation persistence role, also enabled by `npm run db:roles` (D-065);
- `QDRANT_URL` (default `http://localhost:6333`) and optional `KNOWLEDGE_COLLECTION` (default `security_knowledge`, D-071);
- `LANGSMITH_TRACING` / `LANGCHAIN_TRACING_V2` must not be `true` (the service refuses to start, D-060).

## Contracts
After editing `contracts.py`, run `python -m sentinelx_ai.contracts` and commit the regenerated files; a test fails on drift.

## Checks
`python -m ruff check .`, `python -m mypy`, `python -m pytest` (all run by `python scripts/verify.py`).
- Unit tests use a fake LLM and `httpx.MockTransport`.
- `tests/integration/test_ollama_live.py` needs Ollama running with the configured model and asserts a schema-valid verdict.
- `tests/test_tools.py` covers tool schemas, bounds, truncation, error mapping and a static scan for forbidden capabilities, without a database.
- `tests/test_knowledge.py` covers the corpus (curated IDs, sizes, stable point IDs), and the retriever against Qdrant's in-memory mode with a hashing embedder: source references, invalid points, error mapping, lazy client, IPv4 mapping.
- `tests/integration/test_knowledge_live.py` is the Phase 09 exit test. It ingests into a throwaway collection with the real model, checks one row and one point per document, runs 5 retrieval smoke queries with expected source IDs, runs the agent tool as the tools role, and covers idempotent re-ingest with stale-document removal and an unreachable Qdrant or missing collection.
- `tests/test_grounding.py` covers each verdict rule (invented evidence IDs, unknown vs unretrieved MITRE IDs, IDs inside the prose, the severity note/review threshold, retry feedback). `tests/integration/test_review_path_db.py` persists an ungrounded verdict in PostgreSQL and checks the rejection, the audit copy and the findings.
- `tests/test_graph.py` runs the graph with an in-memory store and a scripted LLM: LLM proposals and every fallback reason, the step budget, Ollama outages, verdict retry and review, tool failures, injected newlines, crashes.
- `tests/integration/test_investigation_live.py` is the Phase 08 exit test. It runs the service under uvicorn with PostgreSQL and Ollama, investigates a scenario A incident (202 in under 5 s, 409 while running) to a schema-valid verdict, checks the trace and evidence, and covers the writer-role check and abandoned runs.
- `tests/integration/test_tools_db.py` needs PostgreSQL and npm. It uses the per-module `sentinelx_ai_test_*` database from `tests/integration/conftest.py` (migrated, seeded, `db:roles`), then proves the grants (writes and sensitive reads denied even in a `READ WRITE` transaction), the read-only session, the timeout, each tool's results and that injected log text comes back as plain data.
