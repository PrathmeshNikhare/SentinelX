"""Detection worker (D-046, D-047): Kafka -> contract -> PostgreSQL history -> rules/features/anomaly/risk -> signals.

Usage: python -m sentinelx_detection.worker [--idle-exit SECONDS] [--max-messages N] [--group GROUP_ID]
Offsets are committed only after an event is fully processed (at-least-once with idempotent writes).
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import psycopg
from confluent_kafka import Consumer, KafkaError, TopicPartition

from . import anomaly
from .anomaly import AnomalyModel
from .config import DEFAULT_GROUP_ID, DEFAULT_MODEL_PATH, DEFAULT_TOPIC, optional_env, require_env
from .contract import ContractError, parse_message
from .correlation import plan
from .pipeline import DetectionResult, detect
from .repository import Repository, connect

Outcome = Literal["processed", "invalid", "conflict"]
MAX_BACKOFF_SECONDS = 30.0


def log(severity: str, event: str, /, **fields: Any) -> None:
    """Structured JSON lines; never includes message payloads or credentials."""
    record = {"ts": datetime.now(UTC).isoformat(), "severity": severity, "event": event, **fields}
    print(json.dumps(record, default=str), flush=True)


@dataclass(frozen=True)
class WorkerConfig:
    brokers: str
    topic: str
    group_id: str
    database_url: str

    @staticmethod
    def from_env(group_id: str | None = None) -> WorkerConfig:
        return WorkerConfig(
            brokers=require_env("KAFKA_BROKERS"),
            topic=optional_env("KAFKA_EVENTS_TOPIC", DEFAULT_TOPIC),
            group_id=group_id or optional_env("DETECTION_GROUP_ID", DEFAULT_GROUP_ID),
            database_url=require_env("APP_DATABASE_URL"),
        )


def consumer_settings(config: WorkerConfig) -> dict[str, Any]:
    return {
        "bootstrap.servers": config.brokers,
        "group.id": config.group_id,
        "client.id": "sentinelx-detection",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "broker.address.family": "v4",  # Docker publishes on 127.0.0.1 only (D-040)
    }


def process_message(
    conn: psycopg.Connection[Any], model: AnomalyModel, value: bytes | None
) -> tuple[Outcome, str | None, DetectionResult | None]:
    """One message in one database transaction. Returns (outcome, event_id, result)."""
    try:
        event = parse_message(value)
    except ContractError as error:
        log("warn", "detection.invalid_message", reason=str(error))
        return "invalid", None, None
    with conn.transaction():
        repo = Repository(conn)
        stored = repo.upsert_event(event)
        if not stored.matches:
            # Never attach detection results for different content to the original event.
            log("warn", "detection.event_id_conflict", eventId=event.event_id)
            return "conflict", event.event_id, None
        result = detect(event, repo.load_context(event), model)
        repo.insert_signals(stored.row_id, result.signals)
        alert_id = repo.insert_alert(stored.row_id, result) if result.should_alert else None
        active = repo.active_incident(event.user_id)
        action = plan(event.occurred_at, alert_id is not None, active, repo.is_linked(stored.row_id))
        incident_id = active.incident_id if action == "link" and active is not None else None
        if action == "create":
            incident_id = repo.create_incident(event, result)
            repo.link_lookback(incident_id, event)
        if incident_id is not None:
            repo.link(incident_id, stored.row_id, alert_id)
            repo.refresh_incident(incident_id, event.user_id)
    log(
        "info",
        "detection.processed",
        eventId=event.event_id,
        replay=not stored.inserted,
        signals=[s.rule_name for s in result.signals],
        anomaly=round(result.anomaly_score, 3),
        risk=result.risk_score,
        level=result.risk_level,
        alert=result.should_alert,
        correlation=action,
        incidentId=incident_id,
        modelVersion=result.model_version,
    )
    return "processed", event.event_id, result


def run(
    config: WorkerConfig,
    model: AnomalyModel,
    *,
    should_stop: Callable[[], bool] = lambda: False,
    max_messages: int | None = None,
    idle_exit_seconds: float | None = None,
) -> int:
    """Consumes until stopped, `max_messages` were handled, or the topic was idle for `idle_exit_seconds`."""
    consumer = Consumer(consumer_settings(config))
    consumer.subscribe([config.topic])
    conn: psycopg.Connection[Any] | None = None  # opened lazily so an outage at startup is retried, not fatal
    handled = 0
    backoff = 1.0
    last_activity = time.monotonic()
    log("info", "detection.started", topic=config.topic, group=config.group_id, modelVersion=model.version)
    try:
        while not should_stop():
            message = consumer.poll(1.0)
            if message is None:
                if idle_exit_seconds is not None and time.monotonic() - last_activity > idle_exit_seconds:
                    break
                continue
            error = message.error()
            if error is not None:
                if error.code() != KafkaError._PARTITION_EOF:
                    log("error", "detection.kafka_error", reason=str(error))
                continue
            last_activity = time.monotonic()
            try:
                if conn is None or conn.closed:
                    conn = connect(config.database_url, autocommit=True)
                process_message(conn, model, message.value())
            except (psycopg.OperationalError, psycopg.InterfaceError) as db_error:
                # Database outage: keep the offset, back off, reconnect and retry the same message (no event lost).
                log(
                    "error",
                    "detection.database_unavailable",
                    reason=type(db_error).__name__,
                    retryInSeconds=backoff,
                )
                time.sleep(backoff)
                backoff = min(MAX_BACKOFF_SECONDS, backoff * 2)
                if conn is not None:
                    conn.close()
                    conn = None
                topic, partition, offset = message.topic(), message.partition(), message.offset()
                if topic is not None and partition is not None and offset is not None:
                    consumer.seek(TopicPartition(topic, partition, offset))
                continue
            backoff = 1.0
            consumer.commit(message=message, asynchronous=False)
            handled += 1
            if max_messages is not None and handled >= max_messages:
                break
    finally:
        consumer.close()
        if conn is not None:
            conn.close()
        log("info", "detection.stopped", handled=handled)
    return handled


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m sentinelx_detection.worker")
    parser.add_argument("--idle-exit", type=float, default=None, help="exit after this many idle seconds")
    parser.add_argument("--max-messages", type=int, default=None)
    parser.add_argument("--group", default=None, help="consumer group (a new group replays the topic)")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args(argv)

    model = anomaly.load(args.model)  # fail fast with retrain instructions
    config = WorkerConfig.from_env(args.group)
    stopping = False

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        log("info", "detection.stopping", signal=signum)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run(
        config,
        model,
        should_stop=lambda: stopping,
        max_messages=args.max_messages,
        idle_exit_seconds=args.idle_exit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
