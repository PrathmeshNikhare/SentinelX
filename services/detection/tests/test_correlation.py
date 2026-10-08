"""Pure correlation decisions (D-053) and alert reasons (D-052)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from sentinelx_detection.anomaly import AnomalyModel
from sentinelx_detection.correlation import (
    CORRELATION_WINDOW,
    ActiveIncident,
    alert_reasons,
    incident_title,
    plan,
    within_window,
)

from .conftest import THURSDAY_AFTERNOON, replay, scenario_events

START = THURSDAY_AFTERNOON
INCIDENT = ActiveIncident("inc_0000000000000001", started_at=START, last_activity=START + timedelta(minutes=30))


@pytest.mark.parametrize(
    ("offset", "inside"),
    [
        (-CORRELATION_WINDOW, True),
        (-CORRELATION_WINDOW - timedelta(seconds=1), False),
        (timedelta(minutes=30) + CORRELATION_WINDOW, True),
        (timedelta(minutes=30) + CORRELATION_WINDOW + timedelta(seconds=1), False),
    ],
)
def test_window_spans_an_hour_around_the_incident(offset: timedelta, inside: bool) -> None:
    assert within_window(START + offset, INCIDENT) is inside


@pytest.mark.parametrize(
    ("is_alert", "active", "already_linked", "offset_minutes", "expected"),
    [
        (True, None, False, 0, "create"),
        (False, None, False, 0, "none"),
        (True, INCIDENT, False, 45, "link"),
        (False, INCIDENT, False, 45, "link"),  # non-alerting events complete the timeline
        (True, INCIDENT, False, 200, "create"),  # outside the window: a new incident
        (False, INCIDENT, False, 200, "none"),
        (True, INCIDENT, True, 45, "already_linked"),  # replay never moves an event
        (True, None, True, 0, "already_linked"),
    ],
)
def test_plan(
    is_alert: bool, active: ActiveIncident | None, already_linked: bool, offset_minutes: int, expected: str
) -> None:
    assert plan(START + timedelta(minutes=offset_minutes), is_alert, active, already_linked) == expected


def test_title_uses_the_highest_priority_rule() -> None:
    assert incident_title(["sensitive_file_access", "post_compromise_chain", "brute_force_attempts"], "alice") == (
        "Possible account compromise: alice"
    )
    assert incident_title(["brute_force_attempts"], "alice") == "Brute-force attempts: alice"
    assert incident_title(["new_ip_login", "risky_ip_login"], "carol") == "Login from a risky IP: carol"
    assert incident_title([], "dave") == "Anomalous activity: dave"


def test_alert_reasons_explain_the_score(model: AnomalyModel) -> None:
    result = replay(scenario_events("A", THURSDAY_AFTERNOON), model)[6]  # the PowerShell event
    reasons = alert_reasons(result)
    assert [s["rule"] for s in reasons["signals"]] == ["suspicious_powershell", "post_compromise_chain"]
    components = reasons["components"]
    assert components["rule"] == 85 and components["reputation"] == 90 and components["context"] == 100
    recomputed = 0.45 * components["rule"] + 0.25 * 100 * components["anomaly"] + 0.15 * 90 + 0.15 * 100
    assert abs(recomputed - result.risk_score) <= 0.5 + 0.25 * 100 * 0.00005  # stored anomaly is rounded to 4 dp
    assert reasons["formula"] == "0.45R + 0.25A + 0.15P + 0.15C"
