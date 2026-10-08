"""Usage: python -m sentinelx_ai   (serves on 127.0.0.1:8000 by default; internal only, D-022)."""

from __future__ import annotations

import os
import sys

import uvicorn

from .app import create_app, log
from .config import ConfigError, Settings


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        log("error", "ai.config_invalid", message=str(error))
        return 1
    port = int(os.environ.get("AI_SERVICE_PORT") or 8000)
    log("info", "ai.starting", host="127.0.0.1", port=port, model=settings.ollama_model)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
