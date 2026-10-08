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
from .correlation import CORRELATION_WINDOW, ActiveIncident, alert_reasons, incident_title
from .models import Event, Signal
from .pipeline import DetectionResult

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

    # --- alerts and incidents (D-052, D-053) ---------------------------------------------------------------

    def insert_alert(self, event_row_id: str, result: DetectionResult) -> str:
        """Idempotent on alerts.event_id; returns the alert id (the existing one on replay)."""
        row = self.conn.execute(
            """
            INSERT INTO alerts (event_id, risk_score, anomaly_score, model_version, severity, reasons_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            RETURNING id
            """,
            (
                event_row_id,
                result.risk_score,
                result.anomaly_score,
                result.model_version,
                result.risk_level,
                Jsonb(alert_reasons(result)),
            ),
        ).fetchone()
        if row is None:
            row = self.conn.execute("SELECT id FROM alerts WHERE event_id = %s", (event_row_id,)).fetchone()
        if row is None:  # pragma: no cover - inserted or conflicted inside this transaction
            raise RuntimeError(f"alert for event {event_row_id} missing")
        return str(row[0])

    def is_linked(self, event_row_id: str) -> bool:
        found = self.conn.execute("SELECT 1 FROM incident_events WHERE event_id = %s", (event_row_id,)).fetchone()
        return found is not None

    def active_incident(self, user_id: str) -> ActiveIncident | None:
        """The user's most recent non-resolved incident, row-locked against a concurrent status change."""
        row = self.conn.execute(
            """
            SELECT i.id, i.started_at, max(e.occurred_at) AS last_activity
            FROM incidents i
            JOIN incident_events ie ON ie.incident_id = i.id
            JOIN security_events e ON e.id = ie.event_id
            WHERE i.primary_user_id = %s AND i.status <> 'resolved'
            GROUP BY i.id, i.started_at
            ORDER BY last_activity DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        locked = self.conn.execute("SELECT status FROM incidents WHERE id = %s FOR UPDATE", (row[0],)).fetchone()
        if locked is None or locked[0] == "resolved":  # resolved between the two statements
            return None
        return ActiveIncident(incident_id=str(row[0]), started_at=row[1], last_activity=row[2])

    def create_incident(self, event: Event, result: DetectionResult) -> str:
        row = self.conn.execute(
            """
            INSERT INTO incidents (title, risk_score, severity, primary_user_id, primary_ip, started_at)
            VALUES (%s, %s, %s, %s, %s::inet, %s)
            RETURNING id
            """,
            (
                incident_title((s.rule_name for s in result.signals), event.user_id),
                result.risk_score,
                result.risk_level,
                event.user_id,
                event.source_ip,
                event.occurred_at,
            ),
        ).fetchone()
        if row is None:  # pragma: no cover - INSERT ... RETURNING always returns the row
            raise RuntimeError("incident insert returned no id")
        return str(row[0])

    def link(self, incident_id: str, event_row_id: str, alert_id: str | None) -> None:
        self.conn.execute(
            "INSERT INTO incident_events (incident_id, event_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (incident_id, event_row_id),
        )
        if alert_id is not None:
            self.conn.execute(
                "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (incident_id, alert_id),
            )

    def link_lookback(self, incident_id: str, event: Event) -> None:
        """Context for a new incident: the user's not-yet-linked events in the previous window (D-053)."""
        self.conn.execute(
            """
            INSERT INTO incident_events (incident_id, event_id)
            SELECT %s, e.id FROM security_events e
            WHERE e.user_id = %s AND e.occurred_at >= %s AND e.occurred_at < %s
              AND NOT EXISTS (SELECT 1 FROM incident_events ie WHERE ie.event_id = e.id)
            ON CONFLICT DO NOTHING
            """,
            (incident_id, event.user_id, event.occurred_at - CORRELATION_WINDOW, event.occurred_at),
        )

    def refresh_incident(self, incident_id: str, user_id: str) -> None:
        """Recomputes the incident from its linked rows (idempotent): risk, severity, IP, start, title."""
        rules = self.conn.execute(
            """
            SELECT DISTINCT s.rule_name FROM incident_events ie
            JOIN detection_signals s ON s.event_id = ie.event_id
            WHERE ie.incident_id = %s
            """,
            (incident_id,),
        ).fetchall()
        self.conn.execute(
            """
            WITH top_alert AS (
              SELECT a.risk_score, a.severity, e.source_ip
              FROM incident_alerts ia
              JOIN alerts a ON a.id = ia.alert_id
              JOIN security_events e ON e.id = a.event_id
              WHERE ia.incident_id = %(id)s
              ORDER BY a.risk_score DESC, e.occurred_at ASC
              LIMIT 1
            )
            UPDATE incidents SET
              risk_score = (SELECT risk_score FROM top_alert),
              severity = (SELECT severity FROM top_alert),
              primary_ip = (SELECT source_ip FROM top_alert),
              started_at = (SELECT min(e.occurred_at) FROM incident_events ie
                            JOIN security_events e ON e.id = ie.event_id WHERE ie.incident_id = %(id)s),
              title = %(title)s,
              updated_at = now()
            WHERE id = %(id)s
            """,
            {"id": incident_id, "title": incident_title((str(r[0]) for r in rules), user_id)},
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
