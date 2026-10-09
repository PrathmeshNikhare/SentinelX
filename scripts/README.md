# scripts

Owner: Architect (shared file; docs/19_AGENT_OWNERSHIP.md). Cross-platform helpers written in standard-library Python (D-024).

| Script | Purpose | Phase |
|---|---|---|
| `container-env.sh` | Entrypoint of the app images: rewrites the database URLs from `.env` to `postgres:5432` inside the Compose network, then runs the command (D-079). | 13 |
| `verify.py` | Single verification entrypoint: env, git hygiene, Compose config, infra health and connectivity, web checks (incl. schema drift and DB integration tests from Phase 01, production build + Playwright E2E from Phase 02, Kafka produce/consume from Phase 03), Ollama (required from Phase 06), the ingested knowledge collection (Phase 09) and Python checks. Exit 0 only if nothing FAILs. | 00–09 |
| `test_verify.py` | Unit self-test for `verify.py` helpers (run by `verify.py`). | 00 |

Run from the repo root: `python scripts/verify.py`.
