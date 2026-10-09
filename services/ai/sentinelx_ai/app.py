"""FastAPI AI service (D-057, D-058, D-064). Internal only: 127.0.0.1, every route but /health needs the token."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import psycopg
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import ConfigError, Settings
from .contracts import InvestigationAccepted, InvestigationRequest
from .graph import Deps, Investigator
from .knowledge import QdrantRetriever, SentenceEmbedder, qdrant_client
from .llm import LlmClient, OllamaClient
from .log import log
from .store import Store
from .tools import KNOWLEDGE_TIMEOUT_SECONDS, KnowledgeRetriever, ToolDatabase, build_tools

PUBLIC_PATHS = frozenset({"/health"})
MAX_BODY_BYTES = 16 * 1024


def error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


class Runner(Protocol):
    def run(self, run_id: str, incident_id: str) -> None: ...


def default_retriever(settings: Settings) -> QdrantRetriever:
    """Qdrant over the ingested collection (D-071); the embedding model loads on the first search."""
    connect = lambda: qdrant_client(settings.qdrant_url, int(KNOWLEDGE_TIMEOUT_SECONDS))  # noqa: E731
    return QdrantRetriever(connect, settings.knowledge_collection, SentenceEmbedder())


def create_app(
    settings: Settings,
    llm: LlmClient | None = None,
    store: Store | None = None,
    investigator: Runner | None = None,
    retriever: KnowledgeRetriever | None = None,
) -> FastAPI:
    app = FastAPI(title="SentinelX AI service", docs_url=None, redoc_url=None, openapi_url=None)
    client: LlmClient = llm or OllamaClient(
        settings.ollama_base_url, settings.ollama_model, settings.ollama_timeout_seconds
    )
    runs = store or Store(settings.writer_database_url)
    knowledge = retriever if retriever is not None else default_retriever(settings)
    tools = {t.name: t for t in build_tools(ToolDatabase(settings.tools_database_url), knowledge)}
    runner: Runner = investigator if investigator is not None else Investigator(Deps(runs, client, tools))
    expected = _digest(settings.service_token)

    @app.middleware("http")
    async def authenticate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Runs before routing and body parsing, so unauthenticated callers learn nothing about the API."""
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        presented = header[len("Bearer ") :] if header.startswith("Bearer ") else ""
        if not presented or not hmac.compare_digest(_digest(presented), expected):
            return error(401, "unauthorized", "A valid service token is required.")
        declared = request.headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
            # ponytail: checks Content-Length only; the sole caller (Next.js server) always sends it.
            # Cap the stream instead if another caller appears.
            return error(413, "payload_too_large", f"The body must be at most {MAX_BODY_BYTES} bytes.")
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return error(exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [{"path": ".".join(map(str, e["loc"][1:])) or "(body)", "type": e["type"]} for e in exc.errors()[:20]]
        return error(400, "validation_failed", "The request does not match its contract.", issues=issues)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness only; no dependency details for unauthenticated callers."""
        return {"status": "ok"}

    @app.get("/v1/ready", response_model=None)
    def ready() -> dict[str, str] | JSONResponse:
        if not client.model_available():
            log("warn", "ai.not_ready", model=client.model)
            return error(503, "unavailable", f"Ollama is unreachable or model {client.model!r} is missing.")
        return {"status": "ready", "model": client.model}

    @app.post("/v1/investigations", response_model=None)
    def start_investigation(body: InvestigationRequest, background: BackgroundTasks) -> JSONResponse:
        """Queues a run and returns 202 at once; the graph runs in a background task (D-015)."""
        try:
            started = runs.start_run(body.incident_id)
        except (psycopg.Error, ConfigError) as exc:
            log("error", "ai.store_unavailable", error=type(exc).__name__)
            return error(503, "unavailable", "The investigation database is unavailable.")
        if started.outcome == "in_progress":
            return error(409, "investigation_in_progress", "An investigation of this incident is already running.")
        if started.outcome == "not_found" or started.run_id is None:
            return error(404, "not_found", "Incident not found.")
        background.add_task(runner.run, started.run_id, body.incident_id)
        log(
            "info",
            "ai.investigation_queued",
            runId=started.run_id,
            incidentId=body.incident_id,
            requestedBy=body.requested_by,
        )
        accepted = InvestigationAccepted(investigation_run_id=started.run_id, status="queued")
        return JSONResponse(accepted.model_dump(), status_code=202)

    return app
