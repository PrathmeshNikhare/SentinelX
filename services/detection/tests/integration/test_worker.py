"""Worker against the real stack: Kafka topic -> worker (as sentinelx_app) -> PostgreSQL (D-046, D-047, D-052-D-054).

Uses a throwaway database migrated by the Drizzle migrations (the only DDL source, D-010) and a unique topic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from psycopg import sql

from sentinelx_detection.anomaly import AnomalyModel
from sentinelx_detection.config import REPO_ROOT, require_env
from sentinelx_detection.models import Event
from sentinelx_detection.repository import connect, stored_signal_names
from sentinelx_detection.worker import WorkerConfig, run

from ..conftest import THURSDAY_AFTERNOON, replay, scenario_events

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Stack:
    owner_url: str
    app_url: str
    brokers: str
    topic: str


def with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def npm(script: str, env: dict[str, str]) -> None:
    executable = shutil.which("npm")
    assert executable, "npm is required: Drizzle migrations are the only DDL source"
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        [executable, "run", "--silent", script],
        cwd=REPO_ROOT / "apps" / "web",
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        timeout=180,
    )


DB_PREFIX = "sentinelx_detect_test_"
TOPIC_PREFIX = "security-events-detect-"
STALE_AFTER_SECONDS = 3600


def _is_stale(name: str, prefix: str) -> bool:
    """Names end in a unix timestamp; leftovers from killed runs (no teardown) are swept after an hour."""
    stamp = name.removeprefix(prefix).rsplit("_", 1)[-1].rsplit("-", 1)[-1]
    return stamp.isdigit() and time.time() - int(stamp) > STALE_AFTER_SECONDS


def sweep_stale(owner: str, admin: AdminClient) -> None:
    with connect(owner, autocommit=True) as conn:
        for (name,) in conn.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE %s", (f"{DB_PREFIX}%",)
        ).fetchall():
            if _is_stale(name, DB_PREFIX):
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
    stale_topics = [
        t for t in admin.list_topics(timeout=10).topics if t.startswith(TOPIC_PREFIX) and _is_stale(t, TOPIC_PREFIX)
    ]
    if stale_topics:
        for future in admin.delete_topics(stale_topics).values():
            future.result(timeout=30)


@pytest.fixture(scope="module")
def stack() -> Iterator[Stack]:
    owner, app, brokers = require_env("DATABASE_URL"), require_env("APP_DATABASE_URL"), require_env("KAFKA_BROKERS")
    database = f"{DB_PREFIX}{os.getpid()}_{int(time.time())}"
    with connect(owner, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    owner_test, app_test = with_database(owner, database), with_database(app, database)
    topic = f"{TOPIC_PREFIX}{uuid.uuid4().hex[:8]}-{int(time.time())}"
    admin = AdminClient({"bootstrap.servers": brokers, "broker.address.family": "v4"})
    sweep_stale(owner, admin)
    try:
        for script in ("db:migrate", "db:seed", "db:roles"):
            npm(script, {"DATABASE_URL": owner_test, "APP_DATABASE_URL": app_test})
        admin.create_topics([NewTopic(topic, num_partitions=3, replication_factor=1)])[topic].result(timeout=30)
        yield Stack(owner_test, app_test, brokers, topic)
    finally:
        for future in admin.delete_topics([topic]).values():
            try:
                future.result(timeout=30)
            except Exception:  # noqa: BLE001, S110 - best-effort cleanup of a test topic
                pass
        with connect(owner, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))


def message(event: Event, **overrides: object) -> bytes:
    stamp = event.occurred_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    body = {
        "schema_version": "v1",
        "event_id": event.event_id,
        "occurred_at": stamp,
        "ingested_at": stamp,
        "user_id": event.user_id,
        "source_ip": event.source_ip,
        "event_type": event.event_type,
        "action": event.action,
        "resource": event.resource,
        "status": event.status,
        "metadata": event.metadata,
        **overrides,
    }
    return json.dumps(body).encode()


def publish(stack: Stack, records: list[tuple[str, bytes]]) -> None:
    producer = Producer({"bootstrap.servers": stack.brokers, "broker.address.family": "v4"})
    for key, value in records:
        producer.produce(stack.topic, key=key, value=value, headers=[("schema-version", "v1")])
    assert producer.flush(30) == 0


def consume_all(stack: Stack, model: AnomalyModel, max_messages: int | None = None) -> int:
    """A fresh consumer group reads the topic from the beginning; stops after `max_messages` or 15 idle seconds."""
    config = WorkerConfig(stack.brokers, stack.topic, f"detect-test-{uuid.uuid4().hex[:8]}", stack.app_url)
    return run(config, model, max_messages=max_messages, idle_exit_seconds=15)


def incidents_for(conn: psycopg.Connection[Any], user_id: str) -> list[tuple[Any, ...]]:
    """(id, title, severity, risk, status, started_at, linked events, linked alerts), oldest first."""
    rows: list[tuple[Any, ...]] = conn.execute(
        """
        SELECT i.id, i.title, i.severity::text, i.risk_score, i.status::text, i.started_at,
               (SELECT count(*) FROM incident_events ie WHERE ie.incident_id = i.id),
               (SELECT count(*) FROM incident_alerts ia WHERE ia.incident_id = i.id)
        FROM incidents i WHERE i.primary_user_id = %s ORDER BY i.started_at
        """,
        (user_id,),
    ).fetchall()
    return rows


def test_worker_persists_events_and_the_same_signals_as_the_pure_pipeline(stack: Stack, model: AnomalyModel) -> None:
    scenarios = {sid: scenario_events(sid, THURSDAY_AFTERNOON) for sid in ("A", "B", "C")}
    events = [e for evs in scenarios.values() for e in evs]
    first_a = scenarios["A"][0]
    records = [(e.user_id, message(e)) for e in events]
    records += [
        ("noise", b"{not json"),  # poison message: skipped, never blocks the partition
        ("noise", message(first_a, user_id="Upper.Case")),  # violates the contract (lowercase identity)
        ("alice", message(first_a, resource="tampered-resource")),  # reused event_id with different content
        ("alice", message(first_a)),  # exact duplicate delivery: no second alert, no second link
    ]
    publish(stack, records)

    assert consume_all(stack, model) == len(records)  # every offset committed, including skipped messages

    with connect(stack.owner_url) as conn:
        assert conn.execute("SELECT count(*) FROM security_events").fetchone() == (len(events),)
        stored_resource = conn.execute(
            "SELECT resource FROM security_events WHERE external_event_id = %s", (first_a.event_id,)
        ).fetchone()
        assert stored_resource == (first_a.resource,)  # the conflicting copy changed nothing
        for scenario_list in scenarios.values():
            expected = replay(scenario_list, model)
            for event, result in zip(scenario_list, expected, strict=True):
                assert stored_signal_names(conn, event.event_id) == sorted(s.rule_name for s in result.signals), (
                    event.event_id
                )
        severities = conn.execute("SELECT DISTINCT severity::text FROM detection_signals ORDER BY 1").fetchall()
        assert {r[0] for r in severities} <= {"MEDIUM", "HIGH", "CRITICAL"}

        # Alerts (D-052): exactly the events the pure pipeline says should alert, with explainable reasons.
        expected_alerts = {
            e.event_id: r
            for sid in scenarios
            for e, r in zip(scenarios[sid], replay(scenarios[sid], model), strict=True)
            if r.should_alert
        }
        stored_alerts = conn.execute(
            "SELECT e.external_event_id, a.risk_score, a.severity::text, a.reasons_json FROM alerts a "
            "JOIN security_events e ON e.id = a.event_id"
        ).fetchall()
        assert {row[0] for row in stored_alerts} == set(expected_alerts)
        for external_id, risk, severity, reasons in stored_alerts:
            assert (risk, severity) == (
                expected_alerts[external_id].risk_score,
                expected_alerts[external_id].risk_level,
            )
            assert set(reasons["components"]) == {"rule", "anomaly", "reputation", "context"}
            assert [s["rule"] for s in reasons["signals"]] == [
                s.rule_name for s in expected_alerts[external_id].signals
            ]

        # Incidents (D-053): A -> one compromise incident with its full timeline, C -> one, B -> none.
        a_results = replay(scenarios["A"], model)
        [(_, title, severity, risk, status, started, n_events, n_alerts)] = incidents_for(conn, "alice")
        assert title == "Possible account compromise: alice"
        assert (risk, severity) == (max(r.risk_score for r in a_results), "CRITICAL")
        assert (status, started) == ("open", scenarios["A"][0].occurred_at)  # the 4 failed logins came via lookback
        assert (n_events, n_alerts) == (9, sum(r.should_alert for r in a_results))
        [(_, title_c, severity_c, risk_c, _, _, n_events_c, n_alerts_c)] = incidents_for(conn, "carol")
        c_first = replay(scenarios["C"], model)[0]
        assert title_c == "Login from a risky IP: carol"
        assert (risk_c, severity_c, n_events_c, n_alerts_c) == (c_first.risk_score, c_first.risk_level, 4, 1)
        assert incidents_for(conn, "bob.admin") == []


def test_replaying_the_topic_is_idempotent(stack: Stack, model: AnomalyModel) -> None:
    def snapshot() -> tuple[object, ...]:
        with connect(stack.owner_url) as conn:
            return tuple(
                tuple(conn.execute(query).fetchall())
                for query in (
                    "SELECT count(*) FROM security_events",
                    "SELECT e.external_event_id, s.rule_name, s.rule_score FROM detection_signals s "
                    "JOIN security_events e ON e.id = s.event_id ORDER BY 1, 2",
                    "SELECT id, event_id, risk_score, reasons_json::text FROM alerts ORDER BY 1",
                    "SELECT id, title, risk_score, severity::text, primary_ip::text, started_at "
                    "FROM incidents ORDER BY 1",
                    "SELECT incident_id, event_id FROM incident_events ORDER BY 1, 2",
                    "SELECT incident_id, alert_id FROM incident_alerts ORDER BY 1, 2",
                )
            )

    before = snapshot()
    assert before[0] == ((17,),)
    consume_all(stack, model)  # new consumer group: re-reads the whole topic
    assert snapshot() == before  # no duplicate alerts, incidents or links; nothing re-titled or re-scored


def test_correlation_window_and_resolved_incidents(stack: Stack, model: AnomalyModel) -> None:
    """A burst after the 60-minute window opens a new incident; a resolved incident is never reused (D-053)."""

    def send(base_offset: timedelta) -> None:
        events = scenario_events("A", THURSDAY_AFTERNOON + base_offset)
        publish(stack, [(e.user_id, message(e)) for e in events])
        # A fresh group re-reads everything: earlier messages replay as no-ops, the new ones are processed.
        assert consume_all(stack, model, max_messages=len(events) + stack_messages()) > 0

    def stack_messages() -> int:
        with connect(stack.owner_url) as conn:
            row = conn.execute("SELECT count(*) FROM security_events").fetchone()
        return int(row[0]) + 4 if row else 0  # + the 4 skipped/duplicate messages of the first test

    send(timedelta(hours=3))  # 3 h after the first burst: outside the window
    with connect(stack.owner_url) as conn:
        first, second = incidents_for(conn, "alice")
        assert second[5] == THURSDAY_AFTERNOON + timedelta(hours=3)  # no lookback into the old burst
        assert (second[6], second[1]) == (9, "Possible account compromise: alice")
        conn.execute("UPDATE incidents SET status = 'resolved' WHERE id = %s", (second[0],))
        conn.commit()

    send(timedelta(hours=3, minutes=20))  # inside the window of the second incident, which is now resolved
    with connect(stack.owner_url) as conn:
        incidents = incidents_for(conn, "alice")
        assert len(incidents) == 3
        assert incidents[1][4:] == ("resolved", second[5], 9, second[7])  # untouched after resolution
        assert incidents[2][4] == "open" and incidents[2][6] == 9
        assert incidents[0] == first
