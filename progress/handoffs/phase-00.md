# Phase 00 — Foundation — Handoff

PHASE: 00
STATUS: COMPLETE (receiver accepted 2026-10-08 at Phase 01 start: handoff verification commands reproduced 19/19 PASS up, 4 FAIL exit 1 down; listed files tracked)
GATE: `/verify-phase` APPROVED (2026-10-08)
BASE COMMIT: `f41cc74` (pre-flight). Phase 00 is the commit that adds this file.

## Objective
Repository structure (D-009), Compose infrastructure (D-023), environment, docs/progress, basic test commands and the single verification entrypoint (D-024). No application code.

## Completed work
- `docker-compose.yml`: `postgres:17.6-alpine` (host `127.0.0.1:5433`, D-028), `apache/kafka:4.1.0` single-node KRaft with INTERNAL `kafka:29092` / HOST `localhost:9092` listeners and auto-create disabled, one-shot `kafka-init` creating `security-events` (3 partitions, `--if-not-exists`), `qdrant/qdrant:v1.15.0`. Healthchecks on all three; ports bound to loopback; named volumes `pgdata`, `qdrant_data`. Compose requires `.env` (`${VAR:?}`), so no credentials are embedded in the Compose file.
- `.env.example`: added `POSTGRES_USER/PASSWORD/DB/HOST_PORT`; `DATABASE_URL` now uses 5433.
- `scripts/verify.py` (stdlib only): 19 checks with PASS/FAIL/WARN and a non-zero exit on FAIL. Covers its own self-test, `.env` presence, `.env.example` vs Compose variables, git hygiene, Compose config, container health, PostgreSQL (SSLRequest probe on the host port + password login over the container network), Kafka (host TCP + topic list via the HOST listener), Qdrant `/readyz`, Ollama (WARN-only until Phase 06), web tsc/eslint/vitest, and ruff/mypy/pytest per Python service. `scripts/test_verify.py`: 5 unittest cases for the parsing helpers.
- `apps/web/`: TypeScript toolchain only (strict tsconfig, ESLint flat config with typescript-eslint strict, Vitest) plus a smoke test guarding strict mode. Exact-pinned devDependencies and `package-lock.json`.
- `services/detection/`, `services/ai/`: Python 3.12 toolchain only (`pyproject.toml` tool config with ruff, mypy strict and pytest; empty `requirements.txt`; pinned `requirements-dev.txt`), an empty package and a smoke test.
- READMEs with owner and filling phase for `apps/web`, `services/*`, `contracts/v1`, `fixtures`, `scripts`.
- Docs: `docs/16_ENVIRONMENT.md` rewritten (versions, topology, Windows + POSIX setup, troubleshooting); root `README.md` quickstart; decisions D-028 (Postgres host port 5433) and D-029 (Python 3.12 venvs; tool and image pins).

## Files changed
Added: `docker-compose.yml`, `scripts/{verify.py,test_verify.py,README.md}`, `apps/web/{package.json,package-lock.json,tsconfig.json,eslint.config.js,README.md,src/toolchain.test.ts}`, `services/{detection,ai}/{README.md,pyproject.toml,requirements.txt,requirements-dev.txt,tests/__init__.py,tests/test_smoke.py}`, `services/detection/sentinelx_detection/__init__.py`, `services/ai/sentinelx_ai/__init__.py`, `contracts/v1/README.md`, `fixtures/README.md`, `progress/handoffs/phase-00.md`.
Modified: `.env.example`, `README.md`, `docs/16_ENVIRONMENT.md`, `progress/DECISIONS.md`, `progress/STATUS.md`, `progress/PHASE_LOG.md`, `progress/CURRENT_HANDOFF.md`.

## Tests executed and results
| Command | Result |
|---|---|
| `python scripts/verify.py` (stack up) | 19 checks, 0 failed, 0 warnings, exit 0 |
| `docker compose down` then `python scripts/verify.py` | 4 infra FAILs, exit 1 (exit item 6) |
| `docker compose up -d` and time to healthy | all 3 healthy in 14 s (limit 120 s) |
| `python -m unittest scripts.test_verify` | 5 passed |
| Negative probe: `any` + type error in `apps/web/src` | eslint exit 1, tsc exit 2 (probe removed) |
| Wrong password via container network and via host `psql -p 5433` | both rejected (`password authentication failed`) |
| Host `psql` (native PG18 client) to `localhost:5433` | login OK, server reports PostgreSQL 17.6 |
| `docker compose run --rm kafka-init` (re-run) | exit 0, topic unchanged (idempotent) |
| `kafka-topics.sh --describe --topic security-events` | 3 partitions, RF 1 |
| `npm audit` (apps/web) | 0 vulnerabilities |
| `pip check` (both venvs) | no broken requirements |
| App-code scan (drizzle/FastAPI/Kafka clients/IsolationForest/next) | none |

## Decisions
D-028 (PostgreSQL host port 5433), D-029 (Python 3.12 venvs; tool and image pins). See `progress/DECISIONS.md`.

## Known issues / limitations
- `verify.py` checks PostgreSQL credentials over the container network (pg_hba enforces the password there) and probes the host port with an SSLRequest. Stdlib has no PostgreSQL client. A host-side login was demonstrated manually with the native `psql`. Replace with a psycopg host check once a service ships psycopg (Phase 01+). Marked `ponytail:` in code.
- Kafka host reachability is a TCP connect to `localhost:9092`; the topic is listed through the HOST listener from inside the container. A real host-side produce/consume arrives with the Phase 03 producer. Marked `ponytail:` in code.
- Kafka data is ephemeral (no volume); `kafka-init` recreates the topic on every `up`.
- Ollama on the reference machine has `gemma4:e2b` and `embeddinggemma`, not the `.env.example` default `llama3.2:3b`. Resolve in Phase 06 (open decision).
- Git Bash rewrites absolute container paths in ad-hoc `docker compose exec` commands; use `MSYS_NO_PATHCONV=1`. `verify.py` is unaffected (calls Docker directly).
- `apps/web` has no Next.js yet. Phase 02 must add Next.js to this package and extend `eslint.config.js`, not run `create-next-app` into the directory.

## Deferred work
None from Phase 00 scope.

## Next-agent requirements (Phase 01)
1. Verify this handoff (commands below) and mark Phase 00 `COMPLETE` or `REJECTED`.
2. Before schema work, record nothing new unless needed: D-010, D-012, D-020, D-021 and D-022 already fix the Phase 01 shape.
3. Implement Phase 01 per `docs/07_PHASES.md` and `docs/04_DATA_MODEL.md`: Drizzle in `apps/web` (`src/db/`, `drizzle/`), DB roles, seeds, `ip_reputation` and `mitre_techniques` fixtures.
4. Extend `scripts/verify.py` with the Phase 01 migration/CRUD/role checks.

## Verification commands
```sh
git status                          # clean
docker compose up -d
python scripts/verify.py            # expect: 19 checks: 0 failed, exit 0
docker compose down
python scripts/verify.py            # expect: 4 infra FAILs, exit 1
docker compose up -d
```

## Rollback
`git revert <phase-00 commit>` restores the pre-flight state (`f41cc74`). Infrastructure: `docker compose down -v` removes containers and the `sentinelx_pgdata` / `sentinelx_qdrant_data` volumes. Local-only artifacts to delete if needed: `.env`, `apps/web/node_modules/`, `services/*/.venv/`.
