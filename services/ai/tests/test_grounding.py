"""Evidence-grounded verdict checks (CLAUDE.md evidence policy, D-016, D-073): pure functions, no I/O."""

from __future__ import annotations

from typing import Any

import pytest

from sentinelx_ai.contracts import Verdict
from sentinelx_ai.graph import evidence_entry
from sentinelx_ai.grounding import check_verdict, feedback, rejected, supported_techniques

EV_EVENT, EV_MITRE, EV_KNOWLEDGE, EV_PLAYBOOK = (f"ev_{n:016x}" for n in range(1, 5))
EVIDENCE: list[dict[str, Any]] = [
    evidence_entry(EV_EVENT, ("event", "se_1", "failed login", {"event_id": "se_1"})),
    evidence_entry(EV_MITRE, ("mitre", "T1110", "Brute Force", {"technique_id": "T1110", "found": True})),
    evidence_entry(
        EV_KNOWLEDGE,
        ("knowledge", "kd_1", "T1078", {"source": "mitre-attack", "external_id": "T1078", "document_id": "kd_1"}),
    ),
    evidence_entry(
        EV_PLAYBOOK,
        (
            "knowledge",
            "kd_2",
            "playbook",
            {"source": "sentinelx-playbook", "external_id": "pb-x", "document_id": "kd_2"},
        ),
    ),
]
CURATED = {"T1110", "T1078", "T1059.001", "T1005"}


def verdict(**overrides: Any) -> Verdict:
    base = {
        "verdict": "Possible Account Compromise",
        "confidence": 0.8,
        "severity": "CRITICAL",
        "summary": "Repeated failed logins then a success.",
        "evidence_ids": [EV_EVENT, EV_MITRE],
        "mitre_techniques": ["T1110", "T1078"],
        "recommendations": ["Reset credentials"],
    }
    return Verdict.model_validate({**base, **overrides})


def codes(v: Verdict, severity: str = "CRITICAL") -> list[tuple[str, str]]:
    return [(f.code, f.effect) for f in check_verdict(v, EVIDENCE, severity, CURATED)]  # type: ignore[arg-type]


def test_support_comes_from_found_lookups_and_mitre_knowledge_hits_only() -> None:
    assert supported_techniques(EVIDENCE) == {"T1110", "T1078"}  # the playbook hit adds nothing
    missing = evidence_entry(EV_MITRE, ("mitre", "T9999", "not found", {"technique_id": "T9999", "found": False}))
    assert missing["technique"] is None


def test_a_fully_grounded_verdict_has_no_findings() -> None:
    assert codes(verdict()) == []


def test_invented_evidence_ids_are_rejected() -> None:
    findings = check_verdict(verdict(evidence_ids=[EV_EVENT, "ev_ffffffffffffffff"]), EVIDENCE, "CRITICAL", CURATED)
    assert [(f.code, f.detail, f.effect) for f in findings] == [
        ("unknown_evidence_id", "evidence_ids[1] ev_ffffffffffffffff", "reject")
    ]


@pytest.mark.parametrize(
    ("technique", "code"),
    [("T9999", "unknown_mitre_technique"), ("T1005", "unsupported_mitre_technique")],
)
def test_unknown_or_unretrieved_techniques_are_rejected(technique: str, code: str) -> None:
    assert codes(verdict(mitre_techniques=["T1110", technique])) == [(code, "reject")]


def test_ids_written_into_the_prose_must_resolve_too() -> None:
    prose = verdict(
        summary=f"Brute force (T1110) per {EV_MITRE}; credential dumping T1003 per ev_aaaaaaaaaaaaaaaa.",
        recommendations=["Reset credentials", f"Review {EV_EVENT}"],
    )
    assert [(f.code, f.detail) for f in check_verdict(prose, EVIDENCE, "CRITICAL", CURATED)] == [
        ("unknown_evidence_id", "summary ev_aaaaaaaaaaaaaaaa"),
        ("unsupported_mitre_technique", "summary T1003 not in evidence"),
    ]


@pytest.mark.parametrize(
    ("ai", "deterministic", "expected"),
    [
        ("CRITICAL", "CRITICAL", []),
        ("HIGH", "CRITICAL", [("severity_disagreement", "note")]),
        ("MEDIUM", "CRITICAL", [("severity_disagreement", "review")]),
        ("LOW", "CRITICAL", [("severity_disagreement", "review")]),
        ("CRITICAL", "LOW", [("severity_disagreement", "review")]),
    ],
)
def test_severity_disagreement_is_noted_or_forces_review_never_rejects(
    ai: str, deterministic: str, expected: list[tuple[str, str]]
) -> None:
    assert codes(verdict(severity=ai), deterministic) == expected


def test_feedback_names_references_only() -> None:
    findings = check_verdict(
        verdict(evidence_ids=["ev_ffffffffffffffff"], mitre_techniques=["T1005"], severity="LOW"),
        EVIDENCE,
        "CRITICAL",
        CURATED,
    )
    assert feedback(rejected(findings)) == (
        "unknown_evidence_id: evidence_ids[0] ev_ffffffffffffffff; "
        "unsupported_mitre_technique: mitre_techniques[0] T1005 not in evidence"
    )
