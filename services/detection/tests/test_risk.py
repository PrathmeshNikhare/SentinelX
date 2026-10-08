"""Deterministic risk engine (D-050): formula, rounding, bounds, levels, threshold, monotonicity."""

from __future__ import annotations

import itertools

import pytest

from sentinelx_detection.risk import ALERT_THRESHOLD, context_score, risk_level, risk_score, should_alert


@pytest.mark.parametrize(
    ("rule", "anomaly", "reputation", "context", "expected"),
    [
        (0, 0.0, 0, 0, 0),
        (100, 1.0, 100, 100, 100),
        (85, 0.9, 90, 100, 89),  # 38.25 + 22.5 + 13.5 + 15 = 89.25
        (50, 0.6, 55, 50, 53),  # 22.5 + 15 + 8.25 + 7.5 = 53.25
        (0, 0.8, 0, 0, 20),  # benign event on a known_good IP: anomaly alone stays LOW
        (0, 0.02, 0, 0, 1),  # 0.5 rounds half-up (Python's round() would give 0)
        (0, 0.06, 0, 0, 2),  # 1.5 -> 2
    ],
)
def test_risk_score_formula(rule: int, anomaly: float, reputation: int, context: int, expected: int) -> None:
    assert risk_score(rule, anomaly, reputation, context) == expected


@pytest.mark.parametrize(
    "args",
    [
        (-1, 0.5, 0, 0),
        (101, 0.5, 0, 0),
        (0, -0.1, 0, 0),
        (0, 1.1, 0, 0),
        (0, float("nan"), 0, 0),
        (0, 0.5, 101, 0),
        (0, 0.5, 0, -5),
    ],
)
def test_risk_score_rejects_out_of_range_inputs(args: tuple[int, float, int, int]) -> None:
    with pytest.raises(ValueError):
        risk_score(*args)


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0, "LOW"),
        (29, "LOW"),
        (30, "MEDIUM"),
        (59, "MEDIUM"),
        (60, "HIGH"),
        (79, "HIGH"),
        (80, "CRITICAL"),
        (100, "CRITICAL"),
    ],
)
def test_risk_levels_match_docs_bands(score: int, level: str) -> None:
    assert risk_level(score) == level


def test_alert_threshold() -> None:
    assert ALERT_THRESHOLD == 40
    assert not should_alert(39)
    assert should_alert(40)


def test_context_score_counts_distinct_rules_capped() -> None:
    assert context_score([]) == 0
    assert context_score(["a", "a", "b"]) == 50
    assert context_score(["a", "b", "c", "d", "e"]) == 100


def test_risk_never_decreases_when_any_input_increases() -> None:
    rules, anomalies, reputations, contexts = (
        (0, 35, 60, 85, 100),
        (0.0, 0.3, 0.7, 1.0),
        (0, 25, 55, 90),
        (0, 25, 75, 100),
    )
    for r, a, p, c in itertools.product(rules, anomalies, reputations, contexts):
        base = risk_score(r, a, p, c)
        assert 0 <= base <= 100
        assert risk_score(min(100, r + 10), a, p, c) >= base
        assert risk_score(r, min(1.0, a + 0.1), p, c) >= base
        assert risk_score(r, a, min(100, p + 10), c) >= base
        assert risk_score(r, a, p, min(100, c + 25)) >= base


def test_scenario_b_cannot_alert_without_rules_or_bad_reputation() -> None:
    """Upper bound behind D-050: no rule, known_good IP, no context -> risk <= 25 whatever the anomaly."""
    assert max(risk_score(0, a / 100, 0, 0) for a in range(101)) == 25
