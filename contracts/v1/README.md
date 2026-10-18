# contracts/v1

Versioned cross-service contracts (D-011, D-042). The JSON Schemas are **generated**: the source of truth is `apps/web/src/contracts/security-event.ts`. Regenerate with `npm run contracts:generate` (in `apps/web`); a unit test fails if these files drift. Breaking changes go to `contracts/v2/`.

| File | Contract |
|---|---|
| `security-event.schema.json` | Body of `POST /api/events` |
| `normalized-event.schema.json` | Value of messages on Kafka topic `security-events`, consumed by the detection worker |
| `examples/security-event.json`, `examples/normalized-event.json` | Example pair; the second is the normalization of the first. Every consumer's contract test must parse them. |

| `verdict.schema.json` | Structured investigation verdict (D-059); source: `services/ai/sentinelx_ai/contracts.py` |
| `investigation-request.schema.json`, `investigation-accepted.schema.json` | Next.js server ↔ AI service investigation start (D-015, D-059) |
| `examples/verdict.json`, `examples/investigation-*.json` | Examples parsed by the AI service tests |

Each contract's source is the service that owns it: the zod schemas in `apps/web/src/contracts/` for events (D-042), the Pydantic models in `services/ai` for verdict and investigation contracts (D-059, regenerate with `python -m sentinelx_ai.contracts`).
