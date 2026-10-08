# 14 — API Contracts

Contracts are versioned before cross-service implementation.

`POST /api/events`
```json
{"event_id":"evt_123","timestamp":"2026-01-01T10:00:00Z","user_id":"user_1","source_ip":"192.0.2.10","event_type":"authentication","action":"login","resource":"portal","status":"failed","metadata":{}}
```

`GET /api/incidents`
`GET /api/incidents/:id`
`POST /api/incidents/:id/investigate` -> `202 {"investigation_run_id": "..."}` (asynchronous, D-015)
`GET /api/investigations/:id` -> run status (`queued|running|completed|failed`), `requires_review`, verdict and trace

Internal FastAPI endpoints use explicit Pydantic request/response models. Do not expose agent tools directly to browsers. The FastAPI service is internal: only the Next.js server calls it, authenticated with `AI_SERVICE_TOKEN` (D-022). Shared payload schemas live in `contracts/v1/` (D-011).
