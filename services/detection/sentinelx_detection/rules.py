"""Deterministic detection rules (D-048). Each rule is a pure function of (event, context)."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import timedelta

from .context import DetectionContext
from .models import Event, Signal, severity_for

Rule = Callable[[Event, DetectionContext], Signal | None]

SCRIPT_PROCESSES = frozenset({"powershell.exe", "pwsh.exe", "cmd.exe", "wscript.exe", "cscript.exe", "mshta.exe"})
POWERSHELL = frozenset({"powershell.exe", "pwsh.exe"})
POWERSHELL_INDICATORS = {
    "encoded command": re.compile(r"\s-(?:e|en|enc|encodedcommand)\s", re.IGNORECASE),
    "hidden window": re.compile(r"\s-(?:w|windowstyle)\s+hidden\b", re.IGNORECASE),
    "invoke-expression": re.compile(r"\b(?:iex|invoke-expression)\b", re.IGNORECASE),
    "download cradle": re.compile(r"(?:downloadstring|net\.webclient)", re.IGNORECASE),
    "base64 decoding": re.compile(r"frombase64string", re.IGNORECASE),
}
SENSITIVE_LABELS = frozenset({"confidential", "restricted", "secret"})
SENSITIVE_PATH = re.compile(r"payroll|salary|finance|[\\/]hr[\\/]|credential|password|secret", re.IGNORECASE)


def _signal(rule_name: str, score: int, reason: str) -> Signal:
    return Signal(rule_name=rule_name, rule_score=score, severity=severity_for(score), reason=reason)


def process_name(resource: str) -> str:
    return re.split(r"[\\/]", resource)[-1].lower()


def is_script_process(event: Event) -> bool:
    return event.event_type == "process" and process_name(event.resource) in SCRIPT_PROCESSES


def is_sensitive_resource(event: Event) -> bool:
    if event.event_type != "file_access":
        return False
    label = event.metadata.get("sensitivity")
    return (isinstance(label, str) and label.lower() in SENSITIVE_LABELS) or bool(SENSITIVE_PATH.search(event.resource))


def failed_logins_within(event: Event, ctx: DetectionContext, window: timedelta, include_current: bool) -> int:
    since = event.occurred_at - window
    prior = sum(1 for e in ctx.prior_events if e.is_failed_login and e.occurred_at >= since)
    return prior + (1 if include_current and event.is_failed_login else 0)


def brute_force_attempts(event: Event, ctx: DetectionContext) -> Signal | None:
    if not event.is_failed_login:
        return None
    failures = failed_logins_within(event, ctx, timedelta(minutes=10), include_current=True)
    if failures < 5:
        return None
    return _signal("brute_force_attempts", 60, f"{failures} failed logins for {event.user_id} within 10 minutes")


def login_after_failures(event: Event, ctx: DetectionContext) -> Signal | None:
    if not event.is_successful_login:
        return None
    failures = failed_logins_within(event, ctx, timedelta(minutes=15), include_current=False)
    if failures < 3:
        return None
    return _signal("login_after_failures", 75, f"successful login after {failures} failed logins within 15 minutes")


def new_ip_login(event: Event, ctx: DetectionContext) -> Signal | None:
    if not event.is_successful_login or event.source_ip in ctx.known_ips:
        return None
    if ctx.reputation is not None and ctx.reputation.level == "known_good":
        return None
    return _signal("new_ip_login", 35, f"first successful login from {event.source_ip} for {event.user_id} in 30 days")


def risky_ip_login(event: Event, ctx: DetectionContext) -> Signal | None:
    if not event.is_successful_login or ctx.reputation is None:
        return None
    score = {"suspicious": 50, "malicious": 80}.get(ctx.reputation.level)
    if score is None:
        return None
    return _signal("risky_ip_login", score, f"successful login from {ctx.reputation.level} IP {event.source_ip}")


def suspicious_powershell(event: Event, ctx: DetectionContext) -> Signal | None:
    if event.event_type != "process" or process_name(event.resource) not in POWERSHELL:
        return None
    command_line = event.metadata.get("command_line")
    if not isinstance(command_line, str):
        return None
    padded = f" {command_line} "
    found = [name for name, pattern in POWERSHELL_INDICATORS.items() if pattern.search(padded)]
    if not found:
        return None
    return _signal("suspicious_powershell", 85 if len(found) >= 2 else 70, f"PowerShell with {', '.join(found)}")


def sensitive_file_access(event: Event, ctx: DetectionContext) -> Signal | None:
    if not is_sensitive_resource(event):
        return None
    return _signal("sensitive_file_access", 50, f"{event.action} of sensitive resource {event.resource}")


def privilege_escalation(event: Event, ctx: DetectionContext) -> Signal | None:
    if event.event_type != "privilege_change" or event.status != "success":
        return None
    return _signal("privilege_escalation", 70, f"privilege change '{event.action}' on {event.resource}")


def _country(metadata: dict[str, object]) -> str | None:
    geo = metadata.get("geo")
    country = geo.get("country") if isinstance(geo, dict) else None
    return country if isinstance(country, str) and country else None


def impossible_travel(event: Event, ctx: DetectionContext) -> Signal | None:
    country = _country(event.metadata)
    if not event.is_successful_login or country is None:
        return None
    since = event.occurred_at - timedelta(hours=2)
    for prior in ctx.prior_events:
        other = _country(prior.metadata)
        if prior.is_successful_login and prior.occurred_at >= since and other is not None and other != country:
            return _signal("impossible_travel", 75, f"logins from {other} and {country} within 2 hours")
    return None


def post_compromise_chain(event: Event, ctx: DetectionContext) -> Signal | None:
    if event.event_type not in ("process", "file_access"):
        return None
    since = event.occurred_at - timedelta(minutes=30)
    for prior in ctx.prior_signals:
        compromised = prior.rule_name == "login_after_failures" or (
            prior.rule_name == "risky_ip_login" and prior.rule_score >= 80
        )
        if compromised and prior.occurred_at >= since:
            return _signal(
                "post_compromise_chain",
                85,
                f"{event.event_type} activity within 30 minutes of {prior.rule_name}",
            )
    return None


RULES: tuple[Rule, ...] = (
    brute_force_attempts,
    login_after_failures,
    new_ip_login,
    risky_ip_login,
    suspicious_powershell,
    sensitive_file_access,
    privilege_escalation,
    impossible_travel,
    post_compromise_chain,
)


def evaluate_rules(event: Event, ctx: DetectionContext) -> tuple[Signal, ...]:
    return tuple(signal for rule in RULES if (signal := rule(event, ctx)) is not None)
