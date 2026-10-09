"""AI service settings (D-056, D-058). The single .env lives at the repo root; existing variables take precedence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "contracts" / "v1"
MIN_TOKEN_LENGTH = 32
DEFAULT_TIMEOUT_SECONDS = 120.0  # measured cold call: 40.5 s, of which 11 s model load (D-056)
# langsmith (a langchain-core dependency) uploads traces to a cloud service when any of these is "true" (D-060).
TRACING_VARIABLES = ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2")


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


def validate_service_token(token: str) -> None:
    if len(token) < MIN_TOKEN_LENGTH or "replace-me" in token.lower() or len(set(token)) < 8:
        raise ConfigError(
            f"AI_SERVICE_TOKEN must be a random value of at least {MIN_TOKEN_LENGTH} characters "
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

    @staticmethod
    def from_env() -> Settings:
        load_root_env()
        refuse_cloud_tracing()
        token = os.environ.get("AI_SERVICE_TOKEN", "")
        validate_service_token(token)
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
        return Settings(
            service_token=token,
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434",
            ollama_model=model,
            ollama_timeout_seconds=timeout,
            tools_database_url=urls["AI_TOOLS_DATABASE_URL"],
            writer_database_url=urls["AI_WRITER_DATABASE_URL"],
        )
