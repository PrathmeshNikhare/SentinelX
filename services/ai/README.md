# services/ai

Owner: AI Agent Engineer (docs/19_AGENT_OWNERSHIP.md)

FastAPI AI service (D-057). Internal only: it binds `127.0.0.1:8000`, and every route except `/health` requires `Authorization: Bearer <AI_SERVICE_TOKEN>` (D-058). Phase 06 provides the foundation: settings, contracts, the Ollama adapter and the HTTP surface. Tools (07), the LangGraph investigation (08), RAG (09) and verdict validation (10) build on it.

## Modules (`sentinelx_ai/`)
| Module | Role |
|---|---|
| `config.py` | settings from the repo-root `.env`; refuses unsafe tokens and bad timeouts (D-025) |
| `contracts.py` | Pydantic source of `contracts/v1/{verdict,investigation-request,investigation-accepted}.schema.json` (D-059) |
| `llm.py` | `LlmClient` protocol + `OllamaClient`: schema-constrained `/api/chat`, temperature 0, seed 42, Pydantic re-validation, typed errors (`LlmUnavailable` vs `LlmInvalidOutput`, with the raw output kept for audit) (D-056) |
| `app.py` | `create_app()`: auth middleware before routing, JSON error shape, `GET /health`, `GET /v1/ready`, `POST /v1/investigations` (contract-validated, 501 until Phase 08) |
| `__main__.py` | `python -m sentinelx_ai` |

## Setup and run
Python 3.12 (D-024).

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m sentinelx_ai                 # 127.0.0.1:8000 (AI_SERVICE_PORT overrides)
```

Environment (repo-root `.env`):
- `AI_SERVICE_TOKEN`: required; random, 32+ characters;
- `OLLAMA_BASE_URL` (default `http://localhost:11434`);
- `OLLAMA_MODEL` (`llama3.2:3b`, pulled with `ollama pull llama3.2:3b`);
- optional `OLLAMA_TIMEOUT_SECONDS` (default 120).

## Contracts
After editing `contracts.py`, run `python -m sentinelx_ai.contracts` and commit the regenerated files; a test fails on drift.

## Checks
`python -m ruff check .`, `python -m mypy`, `python -m pytest` (all run by `python scripts/verify.py`).
- Unit tests use a fake LLM and `httpx.MockTransport`.
- `tests/integration/test_ollama_live.py` needs Ollama running with the configured model and asserts a schema-valid verdict.
