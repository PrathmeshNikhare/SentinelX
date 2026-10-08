"""Ollama adapter (D-056, D-057): schema-constrained generation, always re-validated with Pydantic."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

GENERATION_OPTIONS = {"temperature": 0, "seed": 42}  # deterministic (measured, D-056)
CONNECT_TIMEOUT_SECONDS = 5.0
MAX_RAW_CHARS = 20_000


class LlmError(Exception):
    """Base class. Messages never contain model output or prompt text (both may carry injected content)."""


class LlmUnavailable(LlmError):
    """Ollama unreachable, timed out, model missing or HTTP error. The caller preserves state and reports failure."""


class LlmInvalidOutput(LlmError):
    """The model answered, but not with a valid instance of the schema. `raw` is kept for audit (D-019)."""

    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw[:MAX_RAW_CHARS]


class LlmClient(Protocol):
    model: str

    def generate(self, system: str, user: str, schema: type[T]) -> T: ...

    def model_available(self) -> bool: ...


def describe_validation_error(error: ValidationError) -> str:
    """Field paths and error types only: Pydantic's default message quotes the (untrusted) input."""
    parts = [f"{'.'.join(map(str, e['loc'])) or '(root)'}: {e['type']}" for e in error.errors()[:10]]
    return "; ".join(parts)


class OllamaClient:
    def __init__(
        self, base_url: str, model: str, timeout_seconds: float, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.model = model
        self._timeout_seconds = timeout_seconds
        self._http = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS),
            transport=transport,
        )

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "format": schema.model_json_schema(),
            "options": GENERATION_OPTIONS,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            response = self._http.post("/api/chat", json=body)
        except httpx.TimeoutException as error:
            raise LlmUnavailable(f"Ollama did not answer within {self._timeout_seconds:.0f} s") from error
        except httpx.HTTPError as error:
            raise LlmUnavailable(f"Ollama is unreachable ({type(error).__name__})") from error
        if response.status_code == 404:
            raise LlmUnavailable(f"model {self.model!r} is not available in Ollama (ollama pull {self.model})")
        if response.status_code >= 400:
            raise LlmUnavailable(f"Ollama returned HTTP {response.status_code}")
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as error:
            raise LlmInvalidOutput("malformed Ollama response envelope", raw=response.text) from error
        if not isinstance(content, str):
            raise LlmInvalidOutput("Ollama message content is not text", raw=response.text)
        try:
            return schema.model_validate_json(content)
        except ValidationError as error:
            raise LlmInvalidOutput(
                f"output does not match {schema.__name__}: {describe_validation_error(error)}", raw=content
            ) from error

    def model_available(self) -> bool:
        """True when Ollama answers and lists the configured model."""
        try:
            response = self._http.get("/api/tags", timeout=CONNECT_TIMEOUT_SECONDS)
            names = {m.get("name") for m in response.json().get("models", [])} if response.status_code == 200 else set()
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        return self.model in names or f"{self.model}:latest" in names
