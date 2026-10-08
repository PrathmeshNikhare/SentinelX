"""History available to rules and features for one event, strictly before its occurred_at (D-048).

`InMemoryHistory` has the same semantics as the PostgreSQL repository; training and scenario tests use it,
and the worker integration test checks both produce identical results.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .models import Event, Signal

HISTORY_WINDOW = timedelta(hours=24)
KNOWN_IP_WINDOW = timedelta(days=30)
SIGNAL_WINDOW = timedelta(minutes=60)
MAX_PRIOR_EVENTS = 1000
MAX_KNOWN_IPS = 1000
MAX_PRIOR_SIGNALS = 500


@dataclass(frozen=True)
class Reputation:
    level: str
    score: int


@dataclass(frozen=True)
class PriorEvent:
    occurred_at: datetime
    source_ip: str
    event_type: str
    action: str
    status: str
    metadata: dict[str, Any]

    @property
    def is_failed_login(self) -> bool:
        return self.event_type == "authentication" and self.action == "login" and self.status == "failed"

    @property
    def is_successful_login(self) -> bool:
        return self.event_type == "authentication" and self.action == "login" and self.status == "success"


@dataclass(frozen=True)
class PriorSignal:
    occurred_at: datetime
    rule_name: str
    rule_score: int


@dataclass(frozen=True)
class DetectionContext:
    prior_events: tuple[PriorEvent, ...]  # same user, [t - 24 h, t)
    known_ips: frozenset[str]  # same user, successful logins in [t - 30 d, t)
    reputation: Reputation | None  # for the event's source IP
    prior_signals: tuple[PriorSignal, ...]  # same user, [t - 60 min, t)


class InMemoryHistory:
    def __init__(self, reputation: dict[str, Reputation]) -> None:
        self._reputation = reputation
        self._events: dict[str, list[PriorEvent]] = defaultdict(list)
        self._signals: dict[str, list[PriorSignal]] = defaultdict(list)

    def context_for(self, event: Event) -> DetectionContext:
        t = event.occurred_at
        events = self._events[event.user_id]
        prior = [e for e in events if t - HISTORY_WINDOW <= e.occurred_at < t]
        prior.sort(key=lambda e: e.occurred_at, reverse=True)
        # Only successful logins make an IP "known": a brute-forcer's failed attempts must not.
        known = {e.source_ip for e in events if e.is_successful_login and t - KNOWN_IP_WINDOW <= e.occurred_at < t}
        signals = [s for s in self._signals[event.user_id] if t - SIGNAL_WINDOW <= s.occurred_at < t]
        return DetectionContext(
            prior_events=tuple(prior[:MAX_PRIOR_EVENTS]),
            known_ips=frozenset(sorted(known)[:MAX_KNOWN_IPS]),
            reputation=self._reputation.get(event.source_ip),
            prior_signals=tuple(signals[:MAX_PRIOR_SIGNALS]),
        )

    def record(self, event: Event, signals: tuple[Signal, ...]) -> None:
        self._events[event.user_id].append(
            PriorEvent(
                event.occurred_at,
                event.source_ip,
                event.event_type,
                event.action,
                event.status,
                event.metadata,
            )
        )
        self._signals[event.user_id].extend(PriorSignal(event.occurred_at, s.rule_name, s.rule_score) for s in signals)
