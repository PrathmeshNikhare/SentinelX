"""PostgreSQL persistence and history queries for the worker (D-010, D-014, D-046).

Same window semantics as `context.InMemoryHistory`; all queries are parameterized and bounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import psycopg
from psycopg.types.json import Jsonb

from .context import (
    HISTORY_WINDOW,
    KNOWN_IP_WINDOW,
    MAX_KNOWN_IPS,
    MAX_PRIOR_EVENTS,
    MAX_PRIOR_SIGNALS,
    SIGNAL_WINDOW,
    DetectionContext,
    PriorEvent,
    PriorSignal,
    Reputation,
)
from .models import Event, Signal

CONNECT_TIMEOUT_SECONDS = 10  # psycopg's default is unbounded (D-051)


def connect(url: str, *, autocommit: bool = False) -> psycopg.Connection[Any]:
    """psycopg connection that prefers IPv4 for `localhost` and gives up after 10 s (D-051).

    On Windows psycopg tries ::1 first and stalls until the timeout (measured 90 s), while Docker publishes PostgreSQL
    on 127.0.0.1 only. Same idea as `broker.address.family=v4` for Kafka (D-040).
    """
    extra: dict[str, Any] = {"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    if urlsplit(url).hostname == "localhost":
        extra["hostaddr"] = "127.0.0.1"
    return psycopg.connect(url, autocommit=autocommit, **extra)


@dataclass(frozen=True)
class StoredEvent:
    row_id: str
    inserted: bool  # False when external_event_id already existed (replay or duplicate)
    matches: bool  # stored content equals the message (False = an event_id reused with different content)


class Repository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def upsert_event(self, event: Event) -> StoredEvent:
        """Idempotent on external_event_id (D-014). The stored row is never overwritten."""
        row = self.conn.execute(
            """
            INSERT INTO security_events
              (external_event_id, occurred_at, user_id, source_ip, event_type, action, resource, status, metadata_json)
            VALUES (%s, %s, %s, %s::inet, %s, %s, %s, %s, %s)
            ON CONFLICT (external_event_id) DO NOTHING
            RETURNING id
            """,
            (
                event.event_id,
                event.occurred_at,
                event.user_id,
                event.source_ip,
                event.event_type,
                event.action,
                event.resource,
                event.status,
                Jsonb(event.metadata),
            ),
        ).fetchone()
        if row is not None:
            return StoredEvent(row_id=str(row[0]), inserted=True, matches=True)
        stored = self.conn.execute(
            """
            SELECT id, occurred_at, user_id, host(source_ip), event_type, action, resource, status, metadata_json
            FROM security_events WHERE external_event_id = %s
            """,
            (event.event_id,),
        ).fetchone()
        if stored is None:  # pragma: no cover - concurrent delete; the app role cannot delete
            raise RuntimeError(f"event {event.event_id} conflicted but is not stored")
        same = (
            stored[1] == event.occurred_at
            and stored[2] == event.user_id
            and stored[3] == event.source_ip
            and tuple(stored[4:8]) == (event.event_type, event.action, event.resource, event.status)
            and stored[8] == event.metadata
        )
        return StoredEvent(row_id=str(stored[0]), inserted=False, matches=same)

    def load_context(self, event: Event) -> DetectionContext:
        t = event.occurred_at
        prior_rows = self.conn.execute(
            """
            SELECT occurred_at, host(source_ip), event_type, action, status, metadata_json
            FROM security_events
            WHERE user_id = %s AND occurred_at >= %s AND occurred_at < %s
            ORDER BY occurred_at DESC
            LIMIT %s
            """,
            (event.user_id, t - HISTORY_WINDOW, t, MAX_PRIOR_EVENTS),
        ).fetchall()
        known_rows = self.conn.execute(
            """
            SELECT DISTINCT host(source_ip) AS ip
            FROM security_events
            WHERE user_id = %s AND event_type = 'authentication' AND action = 'login' AND status = 'success'
              AND occurred_at >= %s AND occurred_at < %s
            ORDER BY ip
            LIMIT %s
            """,
            (event.user_id, t - KNOWN_IP_WINDOW, t, MAX_KNOWN_IPS),
        ).fetchall()
        reputation_row = self.conn.execute(
            "SELECT reputation::text, score FROM ip_reputation WHERE ip = %s::inet", (event.source_ip,)
        ).fetchone()
        signal_rows = self.conn.execute(
            """
            SELECT e.occurred_at, s.rule_name, s.rule_score
            FROM detection_signals s JOIN security_events e ON e.id = s.event_id
            WHERE e.user_id = %s AND e.occurred_at >= %s AND e.occurred_at < %s
            ORDER BY e.occurred_at
            LIMIT %s
            """,
            (event.user_id, t - SIGNAL_WINDOW, t, MAX_PRIOR_SIGNALS),
        ).fetchall()
        return DetectionContext(
            prior_events=tuple(PriorEvent(r[0], r[1], r[2], r[3], r[4], r[5]) for r in prior_rows),
            known_ips=frozenset(r[0] for r in known_rows),
            reputation=Reputation(level=reputation_row[0], score=int(reputation_row[1])) if reputation_row else None,
            prior_signals=tuple(PriorSignal(r[0], r[1], int(r[2])) for r in signal_rows),
        )

    def insert_signals(self, event_row_id: str, signals: tuple[Signal, ...]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO detection_signals (event_id, rule_name, rule_score, severity, reason)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (event_id, rule_name) DO NOTHING
                """,
                [(event_row_id, s.rule_name, s.rule_score, s.severity, s.reason) for s in signals],
            )


def stored_signal_names(conn: psycopg.Connection[Any], external_event_id: str) -> list[str]:
    """Test/inspection helper."""
    rows = conn.execute(
        """
        SELECT s.rule_name FROM detection_signals s JOIN security_events e ON e.id = s.event_id
        WHERE e.external_event_id = %s ORDER BY s.rule_name
        """,
        (external_event_id,),
    ).fetchall()
    return [str(r[0]) for r in rows]
