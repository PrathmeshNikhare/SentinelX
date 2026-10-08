# SentinelX

AI-assisted security-log analysis and evidence-based threat investigation. A portfolio/research-grade prototype, not an enterprise SIEM. See `docs/01_REQUIREMENTS.md` and `docs/02_ARCHITECTURE.md`.

## Layout
- `apps/web/` — Next.js app (Phase 02+); Drizzle schema, migrations and seeds (Phase 01).
- `services/detection/` — Python detection worker (Phase 03+).
- `services/ai/` — Python FastAPI AI service (Phase 06+).
- `contracts/v1/` — versioned cross-service JSON Schemas.
- `fixtures/` — deterministic synthetic data.
- `scripts/` — `verify.py`, the single verification entrypoint.
- `docker-compose.yml` — PostgreSQL, Kafka (KRaft), Qdrant.
- `CLAUDE.md`, `.claude/`, `docs/`, `progress/` — the Claude Code harness: constitution, agents, commands, specs, project state and handoffs.

## Quickstart
Prerequisites and Windows/POSIX details: `docs/16_ENVIRONMENT.md`.

```sh
cp .env.example .env                 # PowerShell: Copy-Item .env.example .env
docker compose up -d
(cd apps/web && npm ci && npm run db:migrate && npm run db:seed)
# per service: create services/<name>/.venv with Python 3.12, then pip install -r requirements-dev.txt
python scripts/verify.py
```

## Working with the harness
This directory is the SentinelX repository (D-008). Open Claude Code here.

Implement one phase at a time (`00 -> 01 -> ... -> 14`, `docs/07_PHASES.md`) with `/start-phase NN`. At the end of each phase use `/verify-phase`, then `/handoff` only if it returns APPROVED (`docs/18_HANDOFF_PROTOCOL.md`). In a new session use `/resume`.

The repository is deliberately the source of truth so another Claude session or engineer can continue without chat history.
