# 02 — Architecture

```text
Browser -> Next.js App Router
              |-> PostgreSQL
              |-> Kafka: security-events
                       -> Detection Worker
                          -> Rules
                          -> Isolation Forest
                          -> Deterministic Risk Engine
                          -> Alerts / Incidents
                                      -> FastAPI AI Service
                                         -> LangGraph
                                            -> typed read-only tools -> PostgreSQL/local data
                                            -> Qdrant
                                            -> Ollama
                                         -> Structured Verdict
                                         -> Investigation Trace
                                      -> Next.js Incident UI
```

### Boundaries
Web owns UI, session boundary and user-facing APIs. Detection owns rules, features, anomaly model, risk and correlation. AI owns LangGraph, tools, retrieval, LLM adapter, verdict validation and trace creation. PostgreSQL owns persistence.

### Why each boundary exists
Next.js for web/UI, Python for ML/agent ecosystem, Kafka for event-driven processing, Qdrant for semantic retrieval, Ollama for local inference.

Do not add a service without a concrete boundary and documented reason.
