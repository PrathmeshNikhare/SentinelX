"""Each D-048 rule: fires on its pattern, stays silent on near misses."""

from __future__ import annotations

from datetime import timedelta

from sentinelx_detection.context import PriorSignal, Reputation
from sentinelx_detection.rules import (
    brute_force_attempts,
    evaluate_rules,
    impossible_travel,
    login_after_failures,
    new_ip_login,
    post_compromise_chain,
    privilege_escalation,
    risky_ip_login,
    sensitive_file_access,
    suspicious_powershell,
)

from .conftest import THURSDAY_AFTERNOON, make_context, make_event, prior

FAILED = make_event(status="failed")
SUCCESS = make_event(status="success")


def test_brute_force_needs_five_failures_within_ten_minutes() -> None:
    four_prior = tuple(prior(m) for m in (1, 2, 3, 4))
    signal = brute_force_attempts(FAILED, make_context(four_prior))
    assert signal is not None
    assert (signal.rule_score, signal.severity) == (60, "HIGH")
    assert brute_force_attempts(FAILED, make_context(four_prior[:3])) is None  # only 4 in total
    assert brute_force_attempts(FAILED, make_context(tuple(prior(m) for m in (1, 2, 3, 11)))) is None  # one too old
    assert brute_force_attempts(SUCCESS, make_context(four_prior)) is None


def test_login_after_failures_needs_three_prior_failures_within_fifteen_minutes() -> None:
    assert login_after_failures(SUCCESS, make_context(tuple(prior(m) for m in (1, 5, 14)))) is not None
    assert login_after_failures(SUCCESS, make_context(tuple(prior(m) for m in (1, 5, 16)))) is None
    assert login_after_failures(FAILED, make_context(tuple(prior(m) for m in (1, 2, 3)))) is None


def test_new_ip_login_ignores_known_and_known_good_ips() -> None:
    assert new_ip_login(SUCCESS, make_context()) is not None
    assert new_ip_login(SUCCESS, make_context(known_ips=frozenset({"192.0.2.10"}))) is None
    assert new_ip_login(SUCCESS, make_context(reputation=Reputation("known_good", 0))) is None
    assert new_ip_login(FAILED, make_context()) is None


def test_risky_ip_login_scores_by_reputation() -> None:
    assert risky_ip_login(SUCCESS, make_context(reputation=Reputation("unknown", 20))) is None
    suspicious = risky_ip_login(SUCCESS, make_context(reputation=Reputation("suspicious", 55)))
    malicious = risky_ip_login(SUCCESS, make_context(reputation=Reputation("malicious", 90)))
    assert suspicious is not None and suspicious.rule_score == 50
    assert malicious is not None and (malicious.rule_score, malicious.severity) == (80, "CRITICAL")
    assert risky_ip_login(FAILED, make_context(reputation=Reputation("malicious", 90))) is None


def test_suspicious_powershell_counts_indicators() -> None:
    def ps(command_line: str, resource: str = "C:\\Windows\\System32\\powershell.exe") -> int | None:
        event = make_event(
            event_type="process", action="execute", resource=resource, metadata={"command_line": command_line}
        )
        signal = suspicious_powershell(event, make_context())
        return None if signal is None else signal.rule_score

    assert ps("powershell.exe -NoProfile -WindowStyle Hidden -EncodedCommand SQBFAFgA") == 85
    assert ps("powershell.exe -enc SQBFAFgA") == 70
    assert ps("pwsh.exe -c IEX (New-Object Net.WebClient).DownloadString('x')", resource="pwsh.exe") == 85
    assert ps("powershell.exe Get-Service") is None
    assert ps("cmd.exe /c -enc x", resource="cmd.exe") is None  # not PowerShell
    no_command_line = make_event(event_type="process", action="execute", resource="powershell.exe")
    assert suspicious_powershell(no_command_line, make_context()) is None


def test_sensitive_file_access_by_label_or_path() -> None:
    def fires(resource: str, **metadata: object) -> bool:
        event = make_event(event_type="file_access", action="read", resource=resource, metadata=dict(metadata))
        return sensitive_file_access(event, make_context()) is not None

    assert fires("\\\\fs01\\docs\\a.pdf", sensitivity="Confidential")
    assert fires("\\\\fs01\\finance\\payroll-2026.xlsx")
    assert fires("\\\\fs01\\hr\\employee-records.csv")
    assert not fires("\\\\fs01\\engineering\\roadmap.pdf", sensitivity="internal")
    assert not fires("\\\\fs01\\hrm-tools\\readme.txt")  # "hr" only as a path segment
    process = make_event(event_type="process", resource="payroll.exe")
    assert sensitive_file_access(process, make_context()) is None


def test_privilege_escalation_on_successful_privilege_change() -> None:
    event = make_event(event_type="privilege_change", action="add_to_group", resource="Domain Admins")
    assert privilege_escalation(event, make_context()) is not None
    failed = make_event(event_type="privilege_change", action="add_to_group", status="failed")
    assert privilege_escalation(failed, make_context()) is None


def test_impossible_travel_needs_geo_on_both_logins_within_two_hours() -> None:
    event = make_event(metadata={"geo": {"country": "NL"}})
    us_login = prior(60, status="success", metadata={"geo": {"country": "US"}})
    assert impossible_travel(event, make_context((us_login,))) is not None
    assert (
        impossible_travel(event, make_context((prior(130, status="success", metadata={"geo": {"country": "US"}}),)))
        is None
    )
    assert (
        impossible_travel(event, make_context((prior(60, status="success", metadata={"geo": {"country": "NL"}}),)))
        is None
    )
    assert impossible_travel(make_event(), make_context((us_login,))) is None  # no geo on the event


def test_post_compromise_chain_follows_compromise_signals_within_thirty_minutes() -> None:
    file_read = make_event(event_type="file_access", action="read", resource="x")
    recent = THURSDAY_AFTERNOON - timedelta(minutes=10)
    assert post_compromise_chain(
        file_read, make_context(prior_signals=(PriorSignal(recent, "login_after_failures", 75),))
    )
    assert post_compromise_chain(file_read, make_context(prior_signals=(PriorSignal(recent, "risky_ip_login", 80),)))
    assert not post_compromise_chain(
        file_read, make_context(prior_signals=(PriorSignal(recent, "risky_ip_login", 50),))
    )
    old = THURSDAY_AFTERNOON - timedelta(minutes=31)
    assert not post_compromise_chain(
        file_read, make_context(prior_signals=(PriorSignal(old, "login_after_failures", 75),))
    )
    login = make_event()
    assert not post_compromise_chain(
        login, make_context(prior_signals=(PriorSignal(recent, "login_after_failures", 75),))
    )


def test_evaluate_rules_returns_every_hit_in_rule_order() -> None:
    ctx = make_context(tuple(prior(m) for m in (1, 2, 3)), reputation=Reputation("malicious", 90))
    names = [s.rule_name for s in evaluate_rules(SUCCESS, ctx)]
    assert names == ["login_after_failures", "new_ip_login", "risky_ip_login"]
