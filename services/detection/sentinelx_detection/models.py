"""Domain types shared by rules, features, risk and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def severity_for(score: int) -> Severity:
    """Risk bands from docs/01, also used for rule severities (D-048, D-050)."""
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


@dataclass(frozen=True)
class Event:
    """A normalized security event (contracts/v1/normalized-event.schema.json)."""

    event_id: str
    occurred_at: datetime
    user_id: str
    source_ip: str
    event_type: str
    action: str
    resource: str
    status: str
    metadata: dict[str, Any]

    @property
    def is_login(self) -> bool:
        return self.event_type == "authentication" and self.action == "login"

    @property
    def is_failed_login(self) -> bool:
        return self.is_login and self.status == "failed"

    @property
    def is_successful_login(self) -> bool:
        return self.is_login and self.status == "success"


@dataclass(frozen=True)
class Signal:
    """One deterministic rule hit (detection_signals)."""

    rule_name: str
    rule_score: int
    severity: Severity
    reason: str
