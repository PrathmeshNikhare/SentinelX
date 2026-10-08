"""Correlation of alerts into incidents (D-052, D-053). Pure decisions here; SQL in repository.py."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from .pipeline import DetectionResult
from .risk import WEIGHT_ANOMALY, WEIGHT_CONTEXT, WEIGHT_REPUTATION, WEIGHT_RULE

CORRELATION_WINDOW = timedelta(minutes=60)

Action = Literal["already_linked", "link", "create", "none"]

# Highest priority first (D-053). Titles come from deterministic detection, never from the LLM.
TITLE_PRIORITY: tuple[tuple[str, str], ...] = (
    ("post_compromise_chain", "Possible account compromise"),
    ("login_after_failures", "Possible account compromise"),
    ("privilege_escalation", "Privilege escalation"),
    ("suspicious_powershell", "Suspicious PowerShell execution"),
    ("impossible_travel", "Impossible travel"),
    ("brute_force_attempts", "Brute-force attempts"),
    ("risky_ip_login", "Login from a risky IP"),
    ("new_ip_login", "Login from a new IP"),
    ("sensitive_file_access", "Sensitive file access"),
)


@dataclass(frozen=True)
class ActiveIncident:
    """The user's most recent non-resolved incident and its event-time span."""

    incident_id: str
    started_at: datetime
    last_activity: datetime


def within_window(event_time: datetime, incident: ActiveIncident) -> bool:
    return incident.started_at - CORRELATION_WINDOW <= event_time <= incident.last_activity + CORRELATION_WINDOW


def plan(event_time: datetime, is_alert: bool, active: ActiveIncident | None, already_linked: bool) -> Action:
    if already_linked:
        return "already_linked"  # replay: the event's incident membership never changes
    if active is not None and within_window(event_time, active):
        return "link"
    return "create" if is_alert else "none"


def incident_title(rule_names: Iterable[str], user_id: str) -> str:
    names = set(rule_names)
    label = next((title for rule, title in TITLE_PRIORITY if rule in names), "Anomalous activity")
    return f"{label}: {user_id}"


def alert_reasons(result: DetectionResult) -> dict[str, Any]:
    """Why the event scored what it did (stored in alerts.reasons_json)."""
    return {
        "signals": [{"rule": s.rule_name, "score": s.rule_score, "reason": s.reason} for s in result.signals],
        "components": {
            "rule": max((s.rule_score for s in result.signals), default=0),
            "anomaly": round(result.anomaly_score, 4),
            "reputation": result.reputation_score,
            "context": result.context_score,
        },
        "formula": f"{WEIGHT_RULE}R + {WEIGHT_ANOMALY}A + {WEIGHT_REPUTATION}P + {WEIGHT_CONTEXT}C",
    }
