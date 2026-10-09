"""Usage: python -m sentinelx_ai   (serves on 127.0.0.1:8000 by default; internal only, D-022)."""

from __future__ import annotations

import os
import sys
import threading

import psycopg
import uvicorn

from .app import create_app, default_retriever
from .config import ConfigError, Settings
from .log import log
from .store import Store
from .tools import connect_tools


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        log("error", "ai.config_invalid", message=str(error))
        return 1
    try:
        connect_tools(settings.tools_database_url).close()  # refuses any role but sentinelx_ai_tools (D-061)
        store = Store(settings.writer_database_url)
        abandoned = store.abandon_unfinished_runs()  # also proves the writer role (D-065)
    except ConfigError as error:
        log("error", "ai.config_invalid", message=str(error))
        return 1
    except psycopg.Error as error:
        log("error", "ai.database_unavailable", error=type(error).__name__)
        return 1
    if abandoned:
        log("warn", "ai.runs_abandoned", count=abandoned)
    retriever = default_retriever(settings)

    def warm() -> None:
        loaded = retriever.warm()
        log("info" if loaded else "warn", "ai.embedding_model", loaded=loaded, collection=settings.knowledge_collection)

    threading.Thread(target=warm, daemon=True).start()  # the service answers while the model loads
    port = int(os.environ.get("AI_SERVICE_PORT") or 8000)
    log("info", "ai.starting", host="127.0.0.1", port=port, model=settings.ollama_model)
    app = create_app(settings, store=store, retriever=retriever)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
