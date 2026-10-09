# 22 — Clean-Machine Setup and Demo

Runs the whole SentinelX stack in Docker Compose (D-079) and walks demo scenario A (docs/12) from raw events to an evidence-grounded verdict. Development with apps on the host is described in `docs/16_ENVIRONMENT.md`.

## Prerequisites
- Docker Desktop (Windows/macOS) or Docker Engine with Compose v2 (Linux). Allow about 6 GB of memory for Docker. The app images take about 4.4 GB of disk (AI 2.3 GB, web 1.6 GB, detection 0.6 GB), plus the infrastructure images.
- Ollama on the host with the model pulled: `ollama pull llama3.2:3b`. The AI container reaches it at `host.docker.internal:11434`. On Linux, start Ollama with `OLLAMA_HOST=0.0.0.0` so containers can reach it.
- Node.js 24 is needed only for the optional automated demo check (§4).

## 1. Configure
```sh
cp .env.example .env                       # PowerShell: Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # run three times
```
Put the three generated values in `.env` as `AI_SERVICE_TOKEN`, `QDRANT_API_KEY` and `INGEST_API_TOKEN`. The other values are local defaults. Compose and the services refuse to start with a missing or weak secret (D-025, D-078).

## 2. Start the stack
```sh
docker compose --profile app up -d --build
docker compose --profile app ps            # web, ai, detection running; setup and knowledge exited (0)
```
The order is enforced by Compose:
1. PostgreSQL, Kafka and Qdrant start, and `kafka-init` creates the topic.
2. `setup` runs migrations, reference data and role logins.
3. `knowledge` ingests the MITRE and playbook corpus into Qdrant.
4. `ai`, `detection` and `web` start.

The first build takes several minutes (CPU torch, the embedding model and the Next.js build). Later starts take seconds. Only the web console is published to the host: `http://localhost:3000`. The AI service is reachable inside the Compose network only.

## 3. Create an analyst and sign in
```sh
docker compose --profile app run --rm -e ANALYST_PASSWORD='<12+ characters>' setup \
  npm run --silent analyst:create -- analyst@sentinelx.local "Demo Analyst"
```
Open `http://localhost:3000` and sign in.

## 4. Run the demo
**By hand (the story).**
1. Send scenario A, the possible account compromise:
   ```sh
   docker compose --profile app run --rm setup npm run --silent demo:send -- A --url http://web:3000
   ```
   That is 5 failed VPN logins for `alice` from a malicious IP, then a successful login, encoded hidden PowerShell, and reads of payroll and HR files.
2. Open **Incidents**: within seconds, "Possible account compromise: alice" appears with a deterministic risk of about 90 (CRITICAL).
3. Open it and read top to bottom:
   - the **Timeline** shows which events triggered which rules;
   - **Detection signals** show how the risk was computed.
4. Press **Investigate**. The page refreshes itself. On a CPU-only machine the run takes about 1–2 minutes.
5. Follow the **Investigation trace**: each tool the agent chose, marked `llm` or `fallback`.
6. Check the **Evidence**, the **MITRE ATT&CK** techniques with their evidence links, and the **Verdict**:
   - every cited evidence ID links to a stored evidence row;
   - the severity is labelled AI-assessed and shown next to the deterministic one;
   - the confidence is labelled uncalibrated.
7. Read the **Recommendations**: suggestions for the analyst, never actions taken.

Optionally, send scenarios B (benign admin activity, low risk, no incident) and C (anomalous but unclear) to compare.

**Automated check.** The same flow is a Playwright test against the running stack:
```sh
cd apps/web && npm ci && npx playwright install chromium
DEMO_EMAIL=analyst@sentinelx.local DEMO_PASSWORD='<password>' npx playwright test -c playwright.demo.config.ts
```
It passes when the events are ingested and correlated into an incident, the investigation completes, the trace and evidence are present, and either an accepted verdict whose citations all resolve or the review banner is shown. It saves a full-page screenshot to `apps/web/test-results/`.

## 5. Stop or reset
```sh
docker compose --profile app down          # keep data
docker compose --profile app down -v       # also delete PostgreSQL and Qdrant data (a clean slate)
```

## Troubleshooting
- **`ai` unhealthy or investigations failing with "Ollama unavailable".** Check that Ollama runs on the host with `OLLAMA_MODEL` pulled (`curl http://localhost:11434/api/tags`). The service logs are in `docker compose logs ai`.
- **Port 3000 in use.** Stop the host dev server (`npm run dev`) before starting the `web` container.
- **Low memory.** Ollama needs about 2.5 GB while generating, and the AI container about 1 GB. Close other workloads; investigations are the only memory-heavy step.
