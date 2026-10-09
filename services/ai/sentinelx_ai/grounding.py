"""Evidence-grounded verdict validation (CLAUDE.md evidence policy, D-016, D-019, D-073).

Pure functions over a schema-valid verdict and the run's evidence. Findings name IDs and field paths only, never
free model text, so they can be stored, logged and fed back to the model safely.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from .contracts import Severity, Verdict

Effect = Literal["reject", "review", "note"]
SEVERITY_ORDER: Final[Mapping[str, int]] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
REVIEW_SEVERITY_GAP: Final = 2  # D-016: two or more levels apart forces review
EVIDENCE_ID: Final = re.compile(r"\bev_[0-9a-f]{16}\b")
TECHNIQUE_ID: Final = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
MITRE_KNOWLEDGE_SOURCE: Final = "mitre-attack"


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str
    effect: Effect

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "effect": self.effect}


def supported_techniques(evidence: Iterable[Mapping[str, Any]]) -> set[str]:
    """Techniques the run actually retrieved: found MITRE lookups and MITRE knowledge hits."""
    return {e["technique"] for e in evidence if e.get("technique")}


def check_verdict(
    verdict: Verdict,
    evidence: Iterable[Mapping[str, Any]],
    deterministic_severity: Severity,
    known_techniques: set[str],
) -> list[Finding]:
    """Every material reference must resolve to this run's evidence (reject); severity gaps are noted or reviewed."""
    evidence = list(evidence)
    run_ids = {e["id"] for e in evidence}
    supported = supported_techniques(evidence)
    findings: list[Finding] = []

    for index, evidence_id in enumerate(verdict.evidence_ids):
        if evidence_id not in run_ids:
            findings.append(Finding("unknown_evidence_id", f"evidence_ids[{index}] {evidence_id}", "reject"))

    for index, technique in enumerate(verdict.mitre_techniques):
        if technique not in known_techniques:
            findings.append(Finding("unknown_mitre_technique", f"mitre_techniques[{index}] {technique}", "reject"))
        elif technique not in supported:
            findings.append(
                Finding(
                    "unsupported_mitre_technique", f"mitre_techniques[{index}] {technique} not in evidence", "reject"
                )
            )

    # IDs written into the prose must be real too: no invented references anywhere in the verdict.
    texts = {"summary": verdict.summary, **{f"recommendations[{i}]": r for i, r in enumerate(verdict.recommendations)}}
    for field, text in texts.items():
        for evidence_id in sorted(set(EVIDENCE_ID.findall(text)) - run_ids):
            findings.append(Finding("unknown_evidence_id", f"{field} {evidence_id}", "reject"))
        for technique in sorted(set(TECHNIQUE_ID.findall(text)) - supported):
            findings.append(Finding("unsupported_mitre_technique", f"{field} {technique} not in evidence", "reject"))

    gap = abs(SEVERITY_ORDER[verdict.severity] - SEVERITY_ORDER[deterministic_severity])
    if gap:
        effect: Effect = "review" if gap >= REVIEW_SEVERITY_GAP else "note"
        detail = f"AI-assessed {verdict.severity} vs deterministic {deterministic_severity} ({gap} level(s))"
        findings.append(Finding("severity_disagreement", detail, effect))
    return findings


def rejected(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.effect == "reject"]


def feedback(findings: Iterable[Finding]) -> str:
    """Retry instruction naming the failed references (IDs and paths only)."""
    return "; ".join(f"{f.code}: {f.detail}" for f in findings)
