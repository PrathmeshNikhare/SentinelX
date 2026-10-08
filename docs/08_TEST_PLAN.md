# 08 — Test Plan

Unit: Vitest for TypeScript; Pytest for Python. Cover schemas, rules, features, risk, correlation, tools and verdict validation.

Integration: API->Kafka, Kafka->detection, detection->PostgreSQL, incident->FastAPI, agent->tools, Qdrant retrieval, Ollama adapter.

E2E: ingest attack events -> verify alert -> verify incident -> open incident -> investigate -> verify trace -> verify evidence references -> verify verdict.

Negative tests: malformed event, missing fields, invalid IP, oversized query, tool injection, arbitrary SQL attempt, shell attempt, invalid LLM JSON, invalid evidence ID, unknown MITRE ID, unavailable Ollama/Qdrant, duplicate event.

No phase closes with known failing tests unless explicitly documented as deferred.
