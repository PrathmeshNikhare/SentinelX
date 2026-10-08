# contracts/v1

Owner: Architect (docs/19_AGENT_OWNERSHIP.md). Changes affecting another service need review.

Versioned cross-service contracts (D-011, D-042). The JSON Schemas are **generated**: the source of truth is `apps/web/src/contracts/security-event.ts`. Regenerate with `npm run contracts:generate` (in `apps/web`); a unit test fails if these files drift. Breaking changes go to `contracts/v2/`.

| File | Contract |
|---|---|
| `security-event.schema.json` | Body of `POST /api/events` (Phase 03) |
| `normalized-event.schema.json` | Value of messages on Kafka topic `security-events`, consumed by the detection worker (Phase 04) |
| `examples/security-event.json`, `examples/normalized-event.json` | Example pair; the second is the normalization of the first. Every consumer's contract test must parse them. |

Investigation request/response and verdict contracts follow in Phase 06.
