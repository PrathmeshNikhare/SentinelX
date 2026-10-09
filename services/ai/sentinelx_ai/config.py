"""AI service settings (D-056, D-058). The single .env lives at the repo root; existing variables take precedence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "contracts" / "v1"
MIN_TOKEN_LENGTH = 32
DEFAULT_TIMEOUT_SECONDS = 120.0  # measured cold call: 40.5 s, of which 11 s model load (D-056)
# langsmith (a langchain-core dependency) uploads traces to a cloud service when any of these is "true" (D-060).
TRACING_VARIABLES = ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2")


PG_CONNECT_TIMEOUT_SECONDS = 10  # psycopg's default is unbounded (D-051)


def pg_connect_options(url: str, options: str = "-c TimeZone=UTC") -> dict[str, Any]:
    """psycopg keyword arguments: bounded connect, IPv4 for `localhost` (D-051), session settings."""
    extra: dict[str, Any] = {"connect_timeout": PG_CONNECT_TIMEOUT_SECONDS, "options": options}
    if urlsplit(url).hostname == "localhost":
        extra["hostaddr"] = "127.0.0.1"
    return extra


class ConfigError(RuntimeError):
    """Refuse to start rather than run with an unsafe or incomplete configuration (D-025)."""


def load_root_env(path: Path = REPO_ROOT / ".env") -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def validate_secret(name: str, value: str) -> None:
    """Refuse missing, short, placeholder or low-variety secrets (D-025): AI_SERVICE_TOKEN, QDRANT_API_KEY."""
    if len(value) < MIN_TOKEN_LENGTH or "replace-me" in value.lower() or len(set(value)) < 8:
        raise ConfigError(
            f"{name} must be a random value of at least {MIN_TOKEN_LENGTH} characters "
            '(generate: python -c "import secrets; print(secrets.token_urlsafe(32))")'
        )


def refuse_cloud_tracing() -> None:
    enabled = [name for name in TRACING_VARIABLES if os.environ.get(name, "").strip().lower() == "true"]
    if enabled:
        raise ConfigError(f"{', '.join(enabled)} would send investigation data to LangSmith; unset it (D-060)")


@dataclass(frozen=True)
class Settings:
    service_token: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    tools_database_url: str  # sentinelx_ai_tools, SELECT-only (D-061)
    writer_database_url: str  # sentinelx_ai_writer, runs/trace/evidence (D-065)
    qdrant_api_key: str = ""  # D-078; validated by from_env
    qdrant_url: str = "http://localhost:6333"
    knowledge_collection: str = "security_knowledge"  # D-071

    @staticmethod
    def from_env() -> Settings:
        load_root_env()
        refuse_cloud_tracing()
        token = os.environ.get("AI_SERVICE_TOKEN", "")
        validate_secret("AI_SERVICE_TOKEN", token)
        timeout_text = os.environ.get("OLLAMA_TIMEOUT_SECONDS") or str(DEFAULT_TIMEOUT_SECONDS)
        try:
            timeout = float(timeout_text)
        except ValueError as error:
            raise ConfigError("OLLAMA_TIMEOUT_SECONDS must be a number") from error
        if not 1 <= timeout <= 600:
            raise ConfigError("OLLAMA_TIMEOUT_SECONDS must be between 1 and 600")
        model = os.environ.get("OLLAMA_MODEL", "")
        if not model:
            raise ConfigError("OLLAMA_MODEL is not set (copy .env.example to .env at the repo root)")
        urls = {name: os.environ.get(name, "") for name in ("AI_TOOLS_DATABASE_URL", "AI_WRITER_DATABASE_URL")}
        missing = [name for name, url in urls.items() if not url]
        if missing:
            raise ConfigError(f"{', '.join(missing)} not set (copy from .env.example; enable with `npm run db:roles`)")
        qdrant_key = os.environ.get("QDRANT_API_KEY", "")
        validate_secret("QDRANT_API_KEY", qdrant_key)
        return Settings(
            service_token=token,
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434",
            ollama_model=model,
            ollama_timeout_seconds=timeout,
            tools_database_url=urls["AI_TOOLS_DATABASE_URL"],
            writer_database_url=urls["AI_WRITER_DATABASE_URL"],
            qdrant_api_key=qdrant_key,
            qdrant_url=os.environ.get("QDRANT_URL") or "http://localhost:6333",
            knowledge_collection=os.environ.get("KNOWLEDGE_COLLECTION") or "security_knowledge",
        )
