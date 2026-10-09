# 08 — Test Plan

Unit: Vitest for TypeScript; Pytest for Python. Cover schemas, rules, features, risk, correlation, tools and verdict validation.

Integration: API->Kafka, Kafka->detection, detection->PostgreSQL, incident->FastAPI, agent->tools, Qdrant retrieval, Ollama adapter.

E2E: ingest attack events -> verify alert -> verify incident -> open incident -> investigate -> verify trace -> verify evidence references -> verify verdict.

Negative tests: malformed event, missing fields, invalid IP, oversized query, tool injection, arbitrary SQL attempt, shell attempt, invalid LLM JSON, invalid evidence ID, unknown MITRE ID, unavailable Ollama/Qdrant, duplicate event.

No phase closes with known failing tests unless explicitly documented as deferred.

## Coverage map (Phase 13)
All of the following run under `python scripts/verify.py` except the full-stack demo check.

| Plan item | Where |
|---|---|
| Unit: schemas, rules, features, risk, correlation | `apps/web/src/**/*.test.ts` (contracts, normalization, lifecycle, views); `services/detection/tests/test_{rules,features_and_model,risk,correlation,scenarios}.py` |
| Unit: tools, verdict validation | `services/ai/tests/test_{tools,graph,grounding,knowledge,llm,app,contracts_and_config}.py` |
| Integration: API→Kafka | `apps/web/src/ingest/kafka.kafka.test.ts` |
| Integration: Kafka→detection→PostgreSQL | `services/detection/tests/integration/test_worker.py` |
| Integration: incident→FastAPI, agent→tools, Ollama adapter | `services/ai/tests/integration/test_{investigation_live,tools_db,review_path_db,ollama_live}.py` |
| Integration: Qdrant retrieval | `services/ai/tests/integration/test_knowledge_live.py` |
| E2E (web) | `apps/web/e2e/{shell,ingest,walkthrough,security}.spec.ts` against a production build |
| E2E (full stack: ingest → alert → incident → investigate → trace → evidence → verdict) | `apps/web/demo-check/demo.spec.ts` on the Compose stack (`docs/22_DEMO.md`; not in `verify.py`) |
| Negative: malformed event, missing fields, invalid IP, oversized body, duplicate event | `ingest.test.ts`, E2E ingest boundary test, `test_worker.py` (duplicate and poison messages) |
| Negative: oversized query, tool injection, arbitrary SQL, shell attempt | `test_tools.py` (bounds, injected IDs, AST capability scan), `test_tools_db.py` (grants in READ WRITE, injected log text) |
| Negative: invalid LLM JSON, invalid evidence ID, unknown MITRE ID | `test_llm.py`, `test_graph.py`, `test_grounding.py`, `test_review_path_db.py` |
| Negative: unavailable Ollama, Qdrant, AI service, database | `test_graph.py` (Ollama), `test_knowledge_live.py` (Qdrant), E2E (AI service, degraded database) |
