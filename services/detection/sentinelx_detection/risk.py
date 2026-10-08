"""Deterministic risk engine (D-004, D-050). The only place a risk score is computed; the LLM never sets it."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .models import Severity, severity_for

WEIGHT_RULE = 0.45
WEIGHT_ANOMALY = 0.25
WEIGHT_REPUTATION = 0.15
WEIGHT_CONTEXT = 0.15
CONTEXT_POINTS_PER_RULE = 25
ALERT_THRESHOLD = 40


def context_score(recent_rule_names: Iterable[str]) -> int:
    """Correlation term: distinct rules fired for the user in the last 60 minutes, 25 points each, capped at 100."""
    return min(100, CONTEXT_POINTS_PER_RULE * len(set(recent_rule_names)))


def risk_score(rule_score: int, anomaly_score: float, reputation_score: int, context: int) -> int:
    """0-100. Inputs are validated to their ranges; rounding is half-up (Python's round() is banker's rounding)."""
    if not 0 <= rule_score <= 100 or not 0 <= reputation_score <= 100 or not 0 <= context <= 100:
        raise ValueError("rule, reputation and context scores must be within 0-100")
    if not 0.0 <= anomaly_score <= 1.0 or math.isnan(anomaly_score):
        raise ValueError("anomaly score must be within 0-1")
    raw = (
        WEIGHT_RULE * rule_score
        + WEIGHT_ANOMALY * 100 * anomaly_score
        + WEIGHT_REPUTATION * reputation_score
        + WEIGHT_CONTEXT * context
    )
    return max(0, min(100, math.floor(raw + 0.5)))


def risk_level(score: int) -> Severity:
    return severity_for(score)


def should_alert(score: int) -> bool:
    return score >= ALERT_THRESHOLD
