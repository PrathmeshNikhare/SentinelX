# Development

Local-first development without a paid external AI API. Never commit credentials; only `.env.example` is tracked.

## Environment
### Required tools
Versions verified on the reference machine (Windows 11, 2026-10-08). Newer patch versions are fine.

| Tool | Version | Notes |
|---|---|---|
| Git | 2.55 | |
| Node.js | 24.x Active LTS (24.11.0) with npm 11 | `engines.node >= 24` in `apps/web` |
| Python | 3.12.x (3.12.5) | Service venvs use 3.12 for ML wheel availability (D-029). `scripts/verify.py` runs on any Python 3.10+. |
| Docker Desktop | Engine 29, Compose v5 | Infrastructure only (D-023) |
| Ollama | any recent | Runs natively on the host. Required for investigations. |

### Topology (D-023)
| Service | Runs in | Host address |
|---|---|---|
| PostgreSQL 17.6 | Compose | `localhost:5433` (D-028; 5432 is often taken by a native install) |
| Kafka 4.1.0 (single-node KRaft) | Compose | `localhost:9092` (containers use `kafka:29092`) |
| Qdrant 1.15.0 | Compose | `localhost:6333` |
| Ollama | Host | `localhost:11434` (containers use `host.docker.internal:11434`) |
| Next.js, detection worker, FastAPI | Host | also run in Compose (`--profile app`) |

Compose ports bind to `127.0.0.1` only. The `security-events` topic (3 partitions) is created idempotently by the one-shot `kafka-init` service. Kafka data is not persisted across `docker compose down`; PostgreSQL and Qdrant use named volumes (`docker compose down -v` wipes them).

### Setup from a clean clone

#### Windows (PowerShell)
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
services\ai\.venv\Scripts\python -m sentinelx_ai.knowledge                # run from services\ai; downloads the embedding model once

python scripts\verify.py
```

#### POSIX (bash/zsh)
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
(cd services/ai && .venv/bin/python -m sentinelx_ai.knowledge)   # downloads the embedding model once (~90 MB)

python3 scripts/verify.py
```

Required: `ollama pull llama3.2:3b` (D-056); `verify.py` fails when Ollama is unreachable.

### Verification
`python scripts/verify.py` prints `[PASS]`, `[FAIL]` or `[WARN]` per check and exits non-zero on any FAIL. With the Compose stack stopped, the infrastructure checks FAIL by design.

### Running the web console
`cd apps/web && npm run dev`, then open http://localhost:3000 and sign in with the analyst created above. The server connects as `sentinelx_app` (`APP_DATABASE_URL`, D-035). Production mode: `npm run build && npm run start`. Ports: 3000 (dev/start), 3100 and 3101 (E2E servers; must be free when running `verify.py`).

### Event ingestion and demo scenarios
1. Put a token of at least 32 characters in `.env` as `INGEST_API_TOKEN`:
   `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`.
   An empty value disables token auth.
2. Start the app (`npm run dev` or `npm run build && npm run start`).
3. Send a scenario: `npm run demo:send -- A` (or `B`/`C`); add `--url http://localhost:3005` for another port and `--base 2026-01-01T10:00:00Z` for a fixed timeline. Each event is posted to `POST /api/events` and lands on Kafka topic `security-events`.

Events reach PostgreSQL (the console's Events page), and alerting events become incidents (the Incidents page), once the detection worker runs. Optional `KAFKA_EVENTS_TOPIC` overrides the topic (tests use their own, D-045).

### Detection worker
In `services/detection`, train the model once (`python -m sentinelx_detection.train`; deterministic, about 3 s), then run `python -m sentinelx_detection.worker`. Use `--idle-exit 15` to process the backlog and exit. It consumes `security-events`, stores events, detection signals, alerts and incidents as `sentinelx_app`, and logs one JSON line per event with signals, anomaly, risk, the alert decision and the correlation action. To rebuild alerts and incidents for events processed by an older version, replay with a new consumer group: `python -m sentinelx_detection.worker --group backfill-<name> --idle-exit 15` (idempotent, D-055). See `services/detection/README.md`.

### Full stack in Compose
`docker compose --profile app up -d --build` runs the web console, detection worker and AI service in containers next to the infrastructure (D-079). See `docs/setup-and-demo.md` for the clean-machine demo. Stop the host dev server first: the `web` container publishes port 3000. Plain `docker compose up -d` (no profile) keeps the development setup described here.

### AI service
1. Put a random token of 32+ characters in `.env` as `AI_SERVICE_TOKEN`: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The service refuses to start without one.
2. Make sure Ollama is running with `OLLAMA_MODEL` pulled (`ollama pull llama3.2:3b`).
3. In `services/ai`, run `python -m sentinelx_ai`; it serves on `127.0.0.1:8000`.

The service needs `AI_TOOLS_DATABASE_URL` and `AI_WRITER_DATABASE_URL` (both enabled by `npm run db:roles`); it refuses to start otherwise, and at startup marks runs left unfinished by a previous process as failed (D-065). The integration tests create and drop their own `sentinelx_ai_test_*` databases.

Qdrant requires `QDRANT_API_KEY` (D-078): put a random value of 32+ characters in `.env` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) before `docker compose up -d`. Compose, the AI service and the ingestion CLI refuse to start without it.

Knowledge: `python -m sentinelx_ai.knowledge` (owner role, idempotent) ingests the MITRE techniques and playbooks into `knowledge_documents` and the Qdrant collection `security_knowledge` (D-071). Re-run it after editing `fixtures/mitre_techniques.json` or `fixtures/knowledge/playbooks.json`; `verify.py` fails until it has run. The first run downloads `all-MiniLM-L6-v2` from Hugging Face into the user cache; the service then loads it from the cache, warmed in the background at startup (a cold load took about 19 s). The integration tests use throwaway `sentinelx_test_knowledge_*` collections.

Investigation demo: run the web app and the AI service with the same `AI_SERVICE_TOKEN`, open an incident, press **Investigate**, and reload. `GET /api/investigations/<run id>` returns the status, verdict, trace and evidence. A run of the scenario A incident took about 60 s on the reference machine. Leave `LANGSMITH_TRACING`/`LANGCHAIN_TRACING_V2` unset: the service refuses to start when they are `true` (D-060).

The first generation after Ollama loads the model took about 40 s on the reference machine, and warm calls about 5–7 s. See `services/ai/README.md`.

### Database
`npm run db:migrate` and `npm run db:seed` (in `apps/web`) connect with `DATABASE_URL` from the repo-root `.env` as the owner role. Both are idempotent. After editing `src/db/schema.ts`, run `npm run db:generate` and commit the new file in `apps/web/drizzle/`; `verify.py` fails on schema drift. `npm run test:kafka` produces and consumes on the isolated `security-events-test` topic; `npm run test:db` creates and drops its own `sentinelx_test_*` database; `npm run test:e2e` does the same with `sentinelx_e2e`. `npm run db:roles` enables LOGIN for `sentinelx_app`, `sentinelx_ai_tools` and `sentinelx_ai_writer` with the passwords in `APP_DATABASE_URL`, `AI_TOOLS_DATABASE_URL` and `AI_WRITER_DATABASE_URL` (D-061, D-065). Add the AI URLs from `.env.example` to an existing `.env` before running it.

### Troubleshooting
- `docker compose` errors with `set POSTGRES_USER in .env`: copy `.env.example` to `.env`.
- Port already allocated: another process holds 5433, 9092 or 6333. Change `POSTGRES_HOST_PORT` in `.env` (and `DATABASE_URL`) or stop the other process. Kafka's 9092 is tied to its advertised listener and cannot be remapped without editing `docker-compose.yml`.
- Kafka shows `starting` for up to ~40 s on first boot; `verify.py` reports it unhealthy until then.

## Coding standards
TypeScript strict mode; avoid `any`; validate external boundaries; keep server/client separation explicit.

Python type hints; Pydantic/dataclasses for contracts; pure functions where possible; dependency injection for external clients; deterministic tests.

Use explicit names such as `*_id`, `*_at`, `is_*`, `has_*`, `requires_*`.

Expected errors are typed and user-safe. Logs must not expose secrets.

Preferred commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `security:`. Keep commits reversible.

## Test plan
Unit: Vitest for TypeScript; Pytest for Python. Cover schemas, rules, features, risk, correlation, tools and verdict validation.

Integration: API->Kafka, Kafka->detection, detection->PostgreSQL, incident->FastAPI, agent->tools, Qdrant retrieval, Ollama adapter.

E2E: ingest attack events -> verify alert -> verify incident -> open incident -> investigate -> verify trace -> verify evidence references -> verify verdict.

Negative tests: malformed event, missing fields, invalid IP, oversized query, tool injection, arbitrary SQL attempt, shell attempt, invalid LLM JSON, invalid evidence ID, unknown MITRE ID, unavailable Ollama/Qdrant, duplicate event.

No phase closes with known failing tests unless explicitly documented as deferred.

### Coverage map
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
| E2E (full stack: ingest → alert → incident → investigate → trace → evidence → verdict) | `apps/web/demo-check/demo.spec.ts` on the Compose stack (`docs/setup-and-demo.md`; not in `verify.py`) |
| Negative: malformed event, missing fields, invalid IP, oversized body, duplicate event | `ingest.test.ts`, E2E ingest boundary test, `test_worker.py` (duplicate and poison messages) |
| Negative: oversized query, tool injection, arbitrary SQL, shell attempt | `test_tools.py` (bounds, injected IDs, AST capability scan), `test_tools_db.py` (grants in READ WRITE, injected log text) |
| Negative: invalid LLM JSON, invalid evidence ID, unknown MITRE ID | `test_llm.py`, `test_graph.py`, `test_grounding.py`, `test_review_path_db.py` |
| Negative: unavailable Ollama, Qdrant, AI service, database | `test_graph.py` (Ollama), `test_knowledge_live.py` (Qdrant), E2E (AI service, degraded database) |
