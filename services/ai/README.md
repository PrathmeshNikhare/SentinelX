# services/ai

Owner: AI Agent Engineer (docs/19_AGENT_OWNERSHIP.md)

FastAPI AI service: LangGraph investigation, typed read-only tools, Qdrant retrieval, Ollama adapter, verdict validation and trace.

Filled in: Phase 06 (FastAPI, Ollama adapter, verdict schema), 07 (tools), 08 (LangGraph), 09 (RAG/MITRE), 10 (verdict validation). Phase 00 provides only the toolchain and a smoke test.

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
