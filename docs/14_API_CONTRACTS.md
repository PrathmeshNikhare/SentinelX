# 14 — API Contracts

Contracts are versioned before cross-service implementation.

## Browser-facing API (Next.js)
All routes require a valid `sx_session` cookie (D-034). Errors are JSON `{"error": {"code", "message", ...}}`: `401 unauthorized` (no/invalid/revoked session), `404 not_found`, `501 not_implemented` (with `phase`), `503 unavailable` (database unreachable).

| Route | Status (Phase 02) |
|---|---|
| `GET /api/incidents` | implemented: `{incidents: [...]}` (latest 100) |
| `GET /api/incidents/:id` | implemented: `{incident: {..., events: [...]}}`; malformed or unknown id → 404 |
| `PATCH /api/incidents/:id` | implemented (Phase 05, D-054): body exactly `{"status": "open"\|"investigating"\|"resolved"}` → 200 `{incident: {id, status}}`; 400 bad body, 404, 409 `invalid_transition` with `current`, 413, 415 |
| `POST /api/events` | implemented (Phase 03): see below |
| `POST /api/incidents/:id/investigate` | 501, Phases 06–08 |
| `GET /api/investigations/:id` | 501, Phases 06–08 |

`POST /api/events`
```json
{"event_id":"evt_123","timestamp":"2026-01-01T10:00:00Z","user_id":"user_1","source_ip":"192.0.2.10","event_type":"authentication","action":"login","resource":"portal","status":"failed","metadata":{}}
```

`GET /api/incidents`
`GET /api/incidents/:id`
`POST /api/incidents/:id/investigate` -> `202 {"investigation_run_id": "..."}` (asynchronous, D-015)
`GET /api/investigations/:id` -> run status (`queued|running|completed|failed`), `requires_review`, verdict and trace

### `POST /api/events` (D-041, D-043)
- Auth: `Authorization: Bearer <INGEST_API_TOKEN>` (no database access), or an analyst session cookie when no Authorization header is sent.
- Request: `Content-Type: application/json`, body ≤ 16 KiB, matching `contracts/v1/security-event.schema.json` (unknown fields rejected; `__proto__` keys rejected anywhere; timestamp at most 5 min in the future).
- Responses:
  - `202 {"event_id", "status": "accepted"}` once Kafka acknowledged (acks=all);
  - `400 invalid_json` / `400 validation_failed` with `issues: [{path, message}]`;
  - `401`, `413`, `415`;
  - `503` when Kafka does not acknowledge within 8 s.
- Effect: one message on topic `security-events`, key = normalized `user_id`, value = `contracts/v1/normalized-event.schema.json`, headers `schema-version: v1`, `content-type: application/json`. The API never writes to PostgreSQL (D-014).
- The contracts are generated from `apps/web/src/contracts/security-event.ts` with `npm run contracts:generate`; a unit test fails on drift (D-042).

Internal FastAPI endpoints use explicit Pydantic request/response models. Do not expose agent tools directly to browsers. The FastAPI service is internal: only the Next.js server calls it, authenticated with `AI_SERVICE_TOKEN` (D-022). Shared payload schemas live in `contracts/v1/` (D-011).
