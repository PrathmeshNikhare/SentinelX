# scripts

Cross-platform helpers written in standard-library Python (D-024).

| Script | Purpose |
|---|---|
| `container-env.sh` | Entrypoint of the app images: rewrites the database URLs from `.env` to `postgres:5432` inside the Compose network, then runs the command (D-079). |
| `verify.py` | Single verification entrypoint: env, git hygiene, Compose config, infra health and connectivity, web checks (incl. schema drift and DB integration tests, production build + Playwright E2E, Kafka produce/consume), Ollama (required), the ingested knowledge collection and Python checks. Exit 0 only if nothing FAILs. |
| `test_verify.py` | Unit self-test for `verify.py` helpers (run by `verify.py`). |

Run from the repo root: `python scripts/verify.py`.
