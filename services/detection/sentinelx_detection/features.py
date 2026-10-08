"""Isolation Forest feature vector (D-049). The order is part of the model contract (stored in model metadata)."""

from __future__ import annotations

import math
from datetime import timedelta

from .context import DetectionContext
from .models import Event
from .rules import failed_logins_within, is_script_process, is_sensitive_resource

EVENT_TYPES = ("authentication", "process", "file_access", "privilege_change", "network")
UNKNOWN_REPUTATION_SCORE = 25  # also the risk engine's P for unknown IPs (D-050)
COUNT_CAP = 50

FEATURE_NAMES: tuple[str, ...] = (
    "hour_sin",
    "hour_cos",
    "is_weekend",
    "is_failure",
    *(f"type_{t}" for t in EVENT_TYPES),
    "failed_logins_15m",
    "user_events_1h",
    "distinct_ips_24h",
    "is_new_ip",
    "ip_reputation",
    "is_sensitive_resource",
    "is_script_process",
)


def reputation_score(ctx: DetectionContext) -> int:
    return ctx.reputation.score if ctx.reputation is not None else UNKNOWN_REPUTATION_SCORE


def extract(event: Event, ctx: DetectionContext) -> tuple[float, ...]:
    t = event.occurred_at
    hour = t.hour + t.minute / 60
    angle = 2 * math.pi * hour / 24
    events_1h = 1 + sum(1 for e in ctx.prior_events if e.occurred_at >= t - timedelta(hours=1))
    ips_24h = len({e.source_ip for e in ctx.prior_events} | {event.source_ip})
    vector = (
        math.sin(angle),
        math.cos(angle),
        1.0 if t.weekday() >= 5 else 0.0,
        1.0 if event.status == "failed" else 0.0,
        *(1.0 if event.event_type == et else 0.0 for et in EVENT_TYPES),
        float(min(failed_logins_within(event, ctx, timedelta(minutes=15), include_current=True), COUNT_CAP)),
        float(min(events_1h, COUNT_CAP)),
        float(min(ips_24h, COUNT_CAP)),
        0.0 if event.source_ip in ctx.known_ips else 1.0,
        reputation_score(ctx) / 100,
        1.0 if is_sensitive_resource(event) else 0.0,
        1.0 if is_script_process(event) else 0.0,
    )
    assert len(vector) == len(FEATURE_NAMES)  # noqa: S101 - internal invariant of the model contract
    return vector
