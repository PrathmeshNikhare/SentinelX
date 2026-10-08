# services/detection

Owner: Detection Engineer (docs/19_AGENT_OWNERSHIP.md)

Kafka consumer: normalization, deterministic rules, features, Isolation Forest, risk engine and correlation (D-013).

Filled in: Phase 03 (event schema/normalization), Phase 04 (rules, Isolation Forest, risk), Phase 05 (correlation, incidents). Phase 00 provides only the toolchain and a smoke test.

## Setup
Python 3.12 (D-024, docs/16_ENVIRONMENT.md).

```powershell
# Windows PowerShell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

```sh
# POSIX
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## Checks
`python -m ruff check .`, `python -m mypy`, `python -m pytest` (all run by `python scripts/verify.py` at the repo root).
