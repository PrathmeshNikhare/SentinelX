"""Shared fixtures: one trained model per test session and scenario events from fixtures/scenarios."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from sentinelx_detection.anomaly import AnomalyModel, train
from sentinelx_detection.baseline import reputation_from_fixture
from sentinelx_detection.config import FIXTURES_DIR
from sentinelx_detection.context import DetectionContext, InMemoryHistory, PriorEvent, PriorSignal, Reputation
from sentinelx_detection.models import Event
from sentinelx_detection.pipeline import DetectionResult, detect

THURSDAY_AFTERNOON = datetime(2026, 10, 8, 14, 0, tzinfo=UTC)
SATURDAY_NIGHT = datetime(2026, 10, 10, 2, 30, tzinfo=UTC)


@pytest.fixture(scope="session")
def model() -> AnomalyModel:
    return train()


def scenario_file(scenario_id: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (FIXTURES_DIR / "scenarios" / f"scenario-{scenario_id.lower()}.json").read_text(encoding="utf-8")
    )
    return data


def scenario_events(scenario_id: str, base: datetime) -> list[Event]:
    """Fixture events at `base + offset`. Fixtures are already in normalized form (see test_scenarios)."""
    return [
        Event(
            event_id=f"demo-{scenario_id.lower()}-{base.strftime('%Y%m%dT%H%M%SZ')}-{i + 1:02d}",
            occurred_at=base + timedelta(seconds=e["offset_seconds"]),
            user_id=e["user_id"],
            source_ip=e["source_ip"],
            event_type=e["event_type"],
            action=e["action"],
            resource=e["resource"],
            status=e["status"],
            metadata=e.get("metadata", {}),
        )
        for i, e in enumerate(scenario_file(scenario_id)["events"])
    ]


def replay(events: list[Event], model: AnomalyModel) -> list[DetectionResult]:
    """Runs events in order through the in-memory history, exactly like the worker does against PostgreSQL."""
    history = InMemoryHistory(reputation_from_fixture())
    results = []
    for event in events:
        ctx = history.context_for(event)
        result = detect(event, ctx, model)
        history.record(event, result.signals)
        results.append(result)
    return results


def make_event(**overrides: Any) -> Event:
    fields: dict[str, Any] = {
        "event_id": "evt-1",
        "occurred_at": THURSDAY_AFTERNOON,
        "user_id": "alice",
        "source_ip": "192.0.2.10",
        "event_type": "authentication",
        "action": "login",
        "resource": "vpn-portal",
        "status": "success",
        "metadata": {},
    }
    fields.update(overrides)
    return Event(**fields)


def prior(minutes_ago: float, *, status: str = "failed", ip: str = "192.0.2.10", **kw: Any) -> PriorEvent:
    return PriorEvent(
        occurred_at=THURSDAY_AFTERNOON - timedelta(minutes=minutes_ago),
        source_ip=ip,
        event_type=kw.get("event_type", "authentication"),
        action=kw.get("action", "login"),
        status=status,
        metadata=kw.get("metadata", {}),
    )


def make_context(
    prior_events: tuple[PriorEvent, ...] = (),
    known_ips: frozenset[str] = frozenset(),
    reputation: Reputation | None = None,
    prior_signals: tuple[PriorSignal, ...] = (),
) -> DetectionContext:
    return DetectionContext(prior_events, known_ips, reputation, prior_signals)
