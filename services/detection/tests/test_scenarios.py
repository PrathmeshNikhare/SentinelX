"""Phase 04 exit criterion: demo scenarios A/B/C (docs/12) produce the expected signals and risk."""

from __future__ import annotations

from datetime import datetime

import pytest

from sentinelx_detection.anomaly import AnomalyModel

from .conftest import SATURDAY_NIGHT, THURSDAY_AFTERNOON, replay, scenario_events, scenario_file

BASES = pytest.mark.parametrize("base", [THURSDAY_AFTERNOON, SATURDAY_NIGHT], ids=["thu-14h", "sat-02h30"])


@pytest.mark.parametrize("scenario_id", ["A", "B", "C"])
def test_fixtures_are_already_normalized(scenario_id: str) -> None:
    """Lets these tests use fixture values directly instead of re-implementing the TypeScript normalization."""
    for event in scenario_file(scenario_id)["events"]:
        assert event["user_id"] == event["user_id"].lower()
        assert event["action"] == event["action"].lower()
        assert event["resource"] == event["resource"].strip()
        assert ":" not in event["source_ip"]  # IPv4 only, canonical as written


@BASES
def test_scenario_a_possible_account_compromise(model: AnomalyModel, base: datetime) -> None:
    results = replay(scenario_events("A", base), model)
    names = [{s.rule_name for s in r.signals} for r in results]

    assert all(not n for n in names[:4]) and all(not r.should_alert for r in results[:4])
    assert names[4] == {"brute_force_attempts"}
    assert names[5] == {"login_after_failures", "new_ip_login", "risky_ip_login"}
    assert names[6] == {"suspicious_powershell", "post_compromise_chain"}
    assert names[7] == names[8] == {"sensitive_file_access", "post_compromise_chain"}
    assert all(r.risk_level == "CRITICAL" for r in results[5:])
    assert max(r.risk_score for r in results) >= 85  # docs/03: "risk ~90"
    assert all(r.should_alert for r in results[4:])


@BASES
def test_scenario_b_benign_admin_activity(model: AnomalyModel, base: datetime) -> None:
    results = replay(scenario_events("B", base), model)
    assert all(not r.signals for r in results)
    assert all(r.risk_level == "LOW" and not r.should_alert for r in results)


@BASES
def test_scenario_c_anomalous_but_unclear(model: AnomalyModel, base: datetime) -> None:
    results = replay(scenario_events("C", base), model)
    assert {s.rule_name for s in results[0].signals} == {"new_ip_login", "risky_ip_login"}
    assert results[0].risk_level in ("MEDIUM", "HIGH") and results[0].should_alert
    assert all(not r.signals and not r.should_alert for r in results[1:])
    every_rule = {s.rule_name for r in results for s in r.signals}
    assert every_rule.isdisjoint({"brute_force_attempts", "suspicious_powershell", "post_compromise_chain"})


def test_detection_is_deterministic(model: AnomalyModel) -> None:
    first = replay(scenario_events("A", THURSDAY_AFTERNOON), model)
    second = replay(scenario_events("A", THURSDAY_AFTERNOON), model)
    assert first == second
    assert all(r.model_version == model.version for r in first)
