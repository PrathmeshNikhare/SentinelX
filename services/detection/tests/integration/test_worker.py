"""Worker against the real stack: Kafka topic -> worker (as sentinelx_app) -> PostgreSQL (D-046, D-047).

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
from urllib.parse import urlsplit, urlunsplit

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


def consume_all(stack: Stack, model: AnomalyModel) -> int:
    config = WorkerConfig(stack.brokers, stack.topic, f"detect-test-{uuid.uuid4().hex[:8]}", stack.app_url)
    return run(config, model, idle_exit_seconds=15)


def test_worker_persists_events_and_the_same_signals_as_the_pure_pipeline(stack: Stack, model: AnomalyModel) -> None:
    scenarios = {sid: scenario_events(sid, THURSDAY_AFTERNOON) for sid in ("A", "B", "C")}
    events = [e for evs in scenarios.values() for e in evs]
    first_a = scenarios["A"][0]
    records = [(e.user_id, message(e)) for e in events]
    records += [
        ("noise", b"{not json"),  # poison message: skipped, never blocks the partition
        ("noise", message(first_a, user_id="Upper.Case")),  # violates the contract (lowercase identity)
        ("alice", message(first_a, resource="tampered-resource")),  # reused event_id with different content
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


def test_replaying_the_topic_is_idempotent(stack: Stack, model: AnomalyModel) -> None:
    def snapshot() -> tuple[object, ...]:
        with connect(stack.owner_url) as conn:
            events = conn.execute("SELECT count(*) FROM security_events").fetchone()
            signals = conn.execute(
                "SELECT e.external_event_id, s.rule_name, s.rule_score FROM detection_signals s "
                "JOIN security_events e ON e.id = s.event_id ORDER BY 1, 2"
            ).fetchall()
        return (events, tuple(signals))

    before = snapshot()
    assert before[0] == (17,)
    consume_all(stack, model)  # new consumer group: re-reads the whole topic
    assert snapshot() == before
