"""AI-owned contracts (D-059) and settings validation (D-025, D-058)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from sentinelx_ai.config import CONTRACTS_DIR, ConfigError, Settings, validate_secret
from sentinelx_ai.contracts import InvestigationAccepted, InvestigationRequest, Verdict, render_schemas


def example(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((CONTRACTS_DIR / "examples" / name).read_text(encoding="utf-8"))
    return data


def test_generated_contracts_match_the_pydantic_source() -> None:
    for name, content in render_schemas().items():
        assert (CONTRACTS_DIR / name).read_text(encoding="utf-8") == content, (
            f"{name}: run python -m sentinelx_ai.contracts"
        )


def test_examples_satisfy_their_contracts() -> None:
    Verdict.model_validate(example("verdict.json"))
    InvestigationRequest.model_validate(example("investigation-request.json"))
    InvestigationAccepted.model_validate(example("investigation-accepted.json"))


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"unexpected": 1}, "unexpected"),
        ({"confidence": 1.5}, "confidence"),
        ({"confidence": float("nan")}, "confidence"),
        ({"severity": "SEVERE"}, "severity"),
        ({"verdict": "ok"}, "verdict"),
        ({"summary": ""}, "summary"),
        ({"evidence_ids": []}, "evidence_ids"),
        ({"evidence_ids": ["ev_1"]}, "evidence_ids"),  # the CLAUDE.md illustration is not the real ID format (D-030)
        ({"evidence_ids": ["ev_1a2b3c4d5e6f7a8b", "ev_1a2b3c4d5e6f7a8b"]}, "evidence_ids"),
        ({"mitre_techniques": ["T110"]}, "mitre_techniques"),
        ({"mitre_techniques": ["T1110", "T1110"]}, "mitre_techniques"),
        ({"recommendations": []}, "recommendations"),
        ({"recommendations": ["ok"]}, "recommendations"),
        ({"recommendations": [f"Step {i}" for i in range(11)]}, "recommendations"),
    ],
)
def test_verdict_rejects_schema_violations(change: dict[str, Any], field: str) -> None:
    with pytest.raises(ValidationError) as error:
        Verdict.model_validate({**example("verdict.json"), **change})
    assert field in {str(e["loc"][0]) for e in error.value.errors()}


def test_investigation_request_rejects_malformed_ids_and_extra_fields() -> None:
    good = example("investigation-request.json")
    for bad in ({**good, "incident_id": "inc_1"}, {**good, "requested_by": "user_1"}, {**good, "verdict": "x"}):
        with pytest.raises(ValidationError):
            InvestigationRequest.model_validate(bad)


@pytest.mark.parametrize(
    "token", ["", "short", "replace-me" * 5, "a" * 40, "replace-me-with-a-long-random-value-please"]
)
def test_unsafe_service_tokens_are_refused(token: str) -> None:
    with pytest.raises(ConfigError):
        validate_secret("AI_SERVICE_TOKEN", token)


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", "Zk3n-p9Q_r7Xw2Lm8Vt4Yb6Hc1Jd5Gf0Se")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "90")
    settings = Settings.from_env()
    assert (settings.ollama_model, settings.ollama_timeout_seconds) == ("llama3.2:3b", 90.0)
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "0")
    with pytest.raises(ConfigError, match="between"):
        Settings.from_env()
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "soon")
    with pytest.raises(ConfigError, match="number"):
        Settings.from_env()


@pytest.mark.parametrize("key", ["", "short", "replace-me-replace-me-replace-me-0000", "a" * 40])
def test_a_missing_or_weak_qdrant_key_refuses_startup(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", "Zk3n-p9Q_r7Xw2Lm8Vt4Yb6Hc1Jd5Gf0Se")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setenv("QDRANT_API_KEY", key)
    with pytest.raises(ConfigError, match="QDRANT_API_KEY"):
        Settings.from_env()
