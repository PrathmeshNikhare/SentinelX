"""Live Ollama (D-056): the configured model must produce a schema-valid verdict through the real adapter."""

from __future__ import annotations

import os

import pytest

from sentinelx_ai.config import load_root_env
from sentinelx_ai.contracts import Verdict
from sentinelx_ai.llm import LlmInvalidOutput, OllamaClient

pytestmark = pytest.mark.integration

SYSTEM = (
    "You are a security analyst. Use only the evidence provided. Cite evidence IDs exactly as given. "
    "confidence is a number from 0.0 to 1.0, not a percentage."  # Ollama does not enforce numeric bounds (D-068)
)
USER = (
    "Evidence ev_1a2b3c4d5e6f7a8b: 5 failed logins for alice from 203.0.113.45 (malicious) within 2 minutes, "
    "then a successful login.\nEvidence ev_9f8e7d6c5b4a3f2e: encoded, hidden-window PowerShell on alice's workstation."
)


@pytest.fixture(scope="module")
def ollama() -> OllamaClient:
    load_root_env()
    client = OllamaClient(
        os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434",
        os.environ.get("OLLAMA_MODEL") or "llama3.2:3b",
        float(os.environ.get("OLLAMA_TIMEOUT_SECONDS") or 120),
    )
    assert client.model_available(), f"Ollama must be running with {client.model} pulled (ollama pull {client.model})"
    return client


def test_configured_model_returns_a_schema_valid_verdict(ollama: OllamaClient) -> None:
    try:
        verdict = ollama.generate(SYSTEM, USER, Verdict)
    except LlmInvalidOutput as error:  # constrained decoding should prevent this; report it clearly if not
        pytest.fail(f"model output failed validation: {error}")
    assert isinstance(verdict, Verdict)
    assert set(verdict.evidence_ids) <= {"ev_1a2b3c4d5e6f7a8b", "ev_9f8e7d6c5b4a3f2e"}, (
        "cited an evidence ID that was never supplied; Phase 10 must reject such verdicts"
    )
