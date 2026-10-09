"""Shared fixtures for the AI service tests."""

from __future__ import annotations

from typing import TypeVar

import pytest
from pydantic import BaseModel

from sentinelx_ai.config import Settings

T = TypeVar("T", bound=BaseModel)
TOKEN = "test-service-token-0123456789-abcdefghijklmnop"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        service_token=TOKEN,
        ollama_base_url="http://ollama.invalid",
        ollama_model="test-model",
        ollama_timeout_seconds=5,
        tools_database_url="postgresql://sentinelx_ai_tools:x@db.invalid/none",
        writer_database_url="postgresql://sentinelx_ai_writer:x@db.invalid/none",
    )


class FakeLlm:
    """Stand-in for OllamaClient: no network, configurable availability."""

    def __init__(self, available: bool = True) -> None:
        self.model = "test-model"
        self.available = available

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        raise AssertionError("not used in Phase 06 routes")

    def model_available(self) -> bool:
        return self.available
