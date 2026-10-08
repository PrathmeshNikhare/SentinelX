"""AI-owned contracts (D-059): the source of truth for contracts/v1/{verdict,investigation-*}.schema.json.

Usage: python -m sentinelx_ai.contracts   (rewrites the generated files; a test fails on drift)
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .config import CONTRACTS_DIR

EvidenceId = Annotated[str, StringConstraints(pattern=r"^ev_[0-9a-f]{16}$")]  # D-030
TechniqueId = Annotated[str, StringConstraints(pattern=r"^T[0-9]{4}(\.[0-9]{3})?$")]
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
UNIQUE = {"uniqueItems": True}


class Verdict(BaseModel):
    """Structured investigation verdict (CLAUDE.md). Existence of cited IDs is checked in Phase 10."""

    model_config = ConfigDict(extra="forbid", title="SentinelX verdict v1")

    verdict: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0, description="Model-reported, uncalibrated (D-016)")]
    severity: Severity
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    evidence_ids: Annotated[list[EvidenceId], Field(min_length=1, max_length=20, json_schema_extra=UNIQUE)]
    mitre_techniques: Annotated[list[TechniqueId], Field(max_length=10, json_schema_extra=UNIQUE)]
    recommendations: Annotated[
        list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]],
        Field(min_length=1, max_length=10),
    ]

    @field_validator("evidence_ids", "mitre_techniques")
    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("items must be unique")
        return values


class InvestigationRequest(BaseModel):
    """Next.js server -> AI service: start an investigation of one incident (D-015)."""

    model_config = ConfigDict(extra="forbid", title="SentinelX investigation request v1")

    incident_id: Annotated[str, StringConstraints(pattern=r"^inc_[0-9a-f]{16}$")]
    requested_by: Annotated[str, StringConstraints(pattern=r"^an_[0-9a-f]{16}$")]


class InvestigationAccepted(BaseModel):
    """AI service -> Next.js server: the run is queued; poll its status (D-015)."""

    model_config = ConfigDict(extra="forbid", title="SentinelX investigation accepted v1")

    investigation_run_id: Annotated[str, StringConstraints(pattern=r"^run_[0-9a-f]{16}$")]
    status: Literal["queued"]


CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "verdict.schema.json": Verdict,
    "investigation-request.schema.json": InvestigationRequest,
    "investigation-accepted.schema.json": InvestigationAccepted,
}


def render_schemas() -> dict[str, str]:
    """File name -> exact content, shared with the drift test."""
    rendered = {}
    for name, model in CONTRACT_MODELS.items():
        schema = {
            "$id": f"https://sentinelx.local/contracts/v1/{name}",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(),
        }
        rendered[name] = json.dumps(schema, indent=2) + "\n"
    return rendered


def main() -> None:
    for name, content in render_schemas().items():
        (CONTRACTS_DIR / name).write_text(content, encoding="utf-8", newline="\n")
        print(json.dumps({"event": "contracts.generate", "file": f"contracts/v1/{name}"}))


if __name__ == "__main__":
    main()
