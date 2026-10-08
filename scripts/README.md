# scripts

Owner: Architect (shared file; docs/19_AGENT_OWNERSHIP.md). Cross-platform helpers written in standard-library Python (D-024).

| Script | Purpose | Phase |
|---|---|---|
| `verify.py` | Single verification entrypoint: env, git hygiene, Compose config, infra health and connectivity, web checks (incl. schema drift and DB integration tests from Phase 01) and Python checks. Exit 0 only if nothing FAILs. | 00, 01 |
| `test_verify.py` | Unit self-test for `verify.py` helpers (run by `verify.py`). | 00 |

Run from the repo root: `python scripts/verify.py`.
