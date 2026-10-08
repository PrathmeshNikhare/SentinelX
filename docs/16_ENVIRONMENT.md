# 16 — Environment

Local-first development must work without a paid external AI API. Never commit credentials; only `.env.example` is tracked.

## Required tools
Versions verified on the reference machine (Windows 11, 2026-10-08). Newer patch versions are fine.

| Tool | Version | Notes |
|---|---|---|
| Git | 2.55 | |
| Node.js | 24.x Active LTS (24.11.0) with npm 11 | `engines.node >= 24` in `apps/web` |
| Python | 3.12.x (3.12.5) | Service venvs use 3.12 for ML wheel availability (D-029). `scripts/verify.py` runs on any Python 3.10+. |
| Docker Desktop | Engine 29, Compose v5 | Infrastructure only (D-023) |
| Ollama | any recent | Runs natively on the host. Required from Phase 06; WARN-only before that. |

## Topology (D-023)
| Service | Runs in | Host address |
|---|---|---|
| PostgreSQL 17.6 | Compose | `localhost:5433` (D-028; 5432 is often taken by a native install) |
| Kafka 4.1.0 (single-node KRaft) | Compose | `localhost:9092` (containers use `kafka:29092`) |
| Qdrant 1.15.0 | Compose | `localhost:6333` |
| Ollama | Host | `localhost:11434` (containers use `host.docker.internal:11434`) |
| Next.js, detection worker, FastAPI | Host (Phases 00–12) | added to Compose in Phase 13 |

Compose ports bind to `127.0.0.1` only. The `security-events` topic (3 partitions) is created idempotently by the one-shot `kafka-init` service. Kafka data is not persisted across `docker compose down`; PostgreSQL and Qdrant use named volumes (`docker compose down -v` wipes them).

## Setup from a clean clone

### Windows (PowerShell)
```powershell
git clone <repo-url> sentinelx; cd sentinelx
Copy-Item .env.example .env

docker compose up -d

Push-Location apps\web
npm ci; npm run db:migrate; npm run db:seed; npm run db:roles
npx playwright install chromium
$env:ANALYST_PASSWORD = '<at least 12 characters>'
npm run analyst:create -- analyst@sentinelx.local "Demo Analyst"
Remove-Item Env:ANALYST_PASSWORD
Pop-Location

foreach ($s in 'detection','ai') {
  Push-Location "services\$s"
  py -3.12 -m venv .venv
  .venv\Scripts\python -m pip install -r requirements-dev.txt
  Pop-Location
}
services\detection\.venv\Scripts\python -m sentinelx_detection.train   # run from services\detection

python scripts\verify.py
```

### POSIX (bash/zsh)
```sh
git clone <repo-url> sentinelx && cd sentinelx
cp .env.example .env

docker compose up -d

(cd apps/web && npm ci && npm run db:migrate && npm run db:seed && npm run db:roles && npx playwright install chromium)
(cd apps/web && ANALYST_PASSWORD='<at least 12 characters>' npm run analyst:create -- analyst@sentinelx.local "Demo Analyst")

for s in detection ai; do
  (cd "services/$s" && python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt)
done
(cd services/detection && .venv/bin/python -m sentinelx_detection.train)

python3 scripts/verify.py
```

Required from Phase 06: `ollama pull llama3.2:3b` (D-056); `verify.py` fails when Ollama is unreachable.

## Verification
`python scripts/verify.py` prints `[PASS]`, `[FAIL]` or `[WARN]` per check and exits non-zero on any FAIL. With the Compose stack stopped, the infrastructure checks FAIL by design.

## Running the web console
`cd apps/web && npm run dev`, then open http://localhost:3000 and sign in with the analyst created above. The server connects as `sentinelx_app` (`APP_DATABASE_URL`, D-035). Production mode: `npm run build && npm run start`. Ports: 3000 (dev/start), 3100 and 3101 (E2E servers; must be free when running `verify.py`).

## Event ingestion and demo scenarios (Phase 03)
1. Put a token of at least 32 characters in `.env` as `INGEST_API_TOKEN`:
   `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`.
   An empty value disables token auth.
2. Start the app (`npm run dev` or `npm run build && npm run start`).
3. Send a scenario: `npm run demo:send -- A` (or `B`/`C`); add `--url http://localhost:3005` for another port and `--base 2026-01-01T10:00:00Z` for a fixed timeline. Each event is posted to `POST /api/events` and lands on Kafka topic `security-events`.

Events reach PostgreSQL (the console's Events page), and alerting events become incidents (the Incidents page), once the detection worker runs. Optional `KAFKA_EVENTS_TOPIC` overrides the topic (tests use their own, D-045).

## Detection worker (Phase 04)
In `services/detection`, train the model once (`python -m sentinelx_detection.train`; deterministic, about 3 s), then run `python -m sentinelx_detection.worker`. Use `--idle-exit 15` to process the backlog and exit. It consumes `security-events`, stores events, detection signals, alerts and incidents as `sentinelx_app`, and logs one JSON line per event with signals, anomaly, risk, the alert decision and the correlation action. To rebuild alerts and incidents for events processed by an older version, replay with a new consumer group: `python -m sentinelx_detection.worker --group backfill-<name> --idle-exit 15` (idempotent, D-055). See `services/detection/README.md`.

## AI service (Phase 06)
1. Put a random token of 32+ characters in `.env` as `AI_SERVICE_TOKEN`: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The service refuses to start without one.
2. Make sure Ollama is running with `OLLAMA_MODEL` pulled (`ollama pull llama3.2:3b`).
3. In `services/ai`, run `python -m sentinelx_ai`; it serves on `127.0.0.1:8000`.

The first generation after Ollama loads the model took about 40 s on the reference machine, and warm calls about 5–7 s. See `services/ai/README.md`.

## Database
`npm run db:migrate` and `npm run db:seed` (in `apps/web`) connect with `DATABASE_URL` from the repo-root `.env` as the owner role. Both are idempotent. After editing `src/db/schema.ts`, run `npm run db:generate` and commit the new file in `apps/web/drizzle/`; `verify.py` fails on schema drift. `npm run test:kafka` produces and consumes on the isolated `security-events-test` topic; `npm run test:db` creates and drops its own `sentinelx_test_*` database; `npm run test:e2e` does the same with `sentinelx_e2e`. `npm run db:roles` enables LOGIN for `sentinelx_app` with the password in `APP_DATABASE_URL`.

## Troubleshooting
- `docker compose` errors with `set POSTGRES_USER in .env`: copy `.env.example` to `.env`.
- Port already allocated: another process holds 5433, 9092 or 6333. Change `POSTGRES_HOST_PORT` in `.env` (and `DATABASE_URL`) or stop the other process. Kafka's 9092 is tied to its advertised listener and cannot be remapped without editing `docker-compose.yml`.
- Kafka shows `starting` for up to ~40 s on first boot; `verify.py` reports it unhealthy until then.
