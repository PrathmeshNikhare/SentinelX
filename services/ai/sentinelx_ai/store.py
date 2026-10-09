"""Investigation persistence as `sentinelx_ai_writer` (D-022, D-031, D-065).

The writer reads incidents and their linked events/alerts, creates and updates `investigation_runs`, and only appends
to `investigation_trace` and `evidence` (the audit trail is append-only). All queries are fixed and parameterized.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb
from pydantic_core import to_jsonable_python

from .config import ConfigError, pg_connect_options

WRITER_ROLE: Final = "sentinelx_ai_writer"
STATEMENT_TIMEOUT_MS: Final = 5000
MAX_INCIDENT_EVENTS: Final = 20  # newest linked events loaded as initial evidence
MAX_INCIDENT_ALERTS: Final = 10  # highest-risk linked alerts

SourceType = Literal["event", "alert", "user_history", "ip_reputation", "related_logs", "mitre", "knowledge"]
Origin = Literal["llm", "fallback"]


@dataclass(frozen=True)
class IncidentContext:
    incident: dict[str, Any]
    events: list[dict[str, Any]]  # oldest first, each with its rule names under "signals"
    alerts: list[dict[str, Any]]  # highest risk first


@dataclass(frozen=True)
class StartResult:
    outcome: Literal["queued", "not_found", "in_progress"]
    run_id: str | None = None


INCIDENT_SQL: Final = """
SELECT id, title, status::text AS status, risk_score, severity::text AS severity, primary_user_id,
       host(primary_ip) AS primary_ip, started_at, updated_at
FROM incidents WHERE id = %(incident_id)s
"""

INCIDENT_EVENTS_SQL: Final = """
SELECT * FROM (
  SELECT e.id AS event_id, e.external_event_id, e.occurred_at, e.user_id, host(e.source_ip) AS source_ip,
         e.event_type, e.action, e.resource, e.status, e.metadata_json AS metadata,
         COALESCE((SELECT array_agg(s.rule_name ORDER BY s.rule_name) FROM detection_signals s WHERE s.event_id = e.id),
                  '{}') AS signals
  FROM incident_events ie JOIN security_events e ON e.id = ie.event_id
  WHERE ie.incident_id = %(incident_id)s
  ORDER BY e.occurred_at DESC, e.id DESC
  LIMIT %(limit)s
) newest ORDER BY occurred_at, event_id
"""

INCIDENT_ALERTS_SQL: Final = """
SELECT a.id AS alert_id, a.event_id, a.risk_score, a.anomaly_score, a.severity::text AS severity,
       a.reasons_json AS reasons
FROM incident_alerts ia JOIN alerts a ON a.id = ia.alert_id
WHERE ia.incident_id = %(incident_id)s
ORDER BY a.risk_score DESC, a.id
LIMIT %(limit)s
"""

CREATE_RUN_SQL: Final = """
INSERT INTO investigation_runs (incident_id)
SELECT i.id FROM incidents i
WHERE i.id = %(incident_id)s
  AND NOT EXISTS (
    SELECT 1 FROM investigation_runs r WHERE r.incident_id = i.id AND r.status IN ('queued', 'running')
  )
RETURNING id
"""

MARK_RUNNING_SQL: Final = """
UPDATE investigation_runs SET status = 'running', started_at = now(), model_name = %(model)s,
       prompt_version = %(prompt_version)s
WHERE id = %(run_id)s AND status = 'queued'
"""

FINISH_RUN_SQL: Final = """
UPDATE investigation_runs
SET status = %(status)s, requires_review = %(requires_review)s, verdict_json = %(verdict)s,
    raw_output_json = %(raw_output)s, validation_errors_json = %(validation_errors)s,
    error_message = %(error_message)s, completed_at = now()
WHERE id = %(run_id)s AND status = 'running'
"""

ABANDON_RUNS_SQL: Final = """
UPDATE investigation_runs
SET status = 'failed', requires_review = true, error_message = %(message)s, completed_at = now()
WHERE status IN ('queued', 'running')
"""

INSERT_TRACE_SQL: Final = """
INSERT INTO investigation_trace (investigation_run_id, step_index, action_type, action_origin, tool_name, input_json,
                                 result_json, evidence_ids_json, retrieval_refs_json)
VALUES (%(run_id)s, %(step_index)s, %(action_type)s, %(origin)s, %(tool_name)s, %(input)s, %(result)s,
        %(evidence_ids)s, %(retrieval_refs)s)
"""

INSERT_EVIDENCE_SQL: Final = """
INSERT INTO evidence (investigation_run_id, source_type, source_id, claim, data_json)
VALUES (%(run_id)s, %(source_type)s, %(source_id)s, %(claim)s, %(data)s)
RETURNING id
"""


def _jsonb(value: Any) -> Jsonb | None:
    """JSON-safe copy (datetimes become ISO strings) for a jsonb column."""
    return None if value is None else Jsonb(to_jsonable_python(value))


def _utc(row: DictRow, *keys: str) -> dict[str, Any]:
    return {**row, **{k: row[k].astimezone(UTC) for k in keys if isinstance(row.get(k), datetime)}}


class Store:
    """One short-lived connection per operation, so a background investigation never holds a connection idle."""

    def __init__(self, url: str) -> None:
        self._url = url

    def _connect(self) -> psycopg.Connection[DictRow]:
        session = f"-c statement_timeout={STATEMENT_TIMEOUT_MS} -c TimeZone=UTC"
        conn = psycopg.connect(self._url, row_factory=dict_row, **pg_connect_options(self._url, session))
        row = conn.execute("SELECT current_user AS role").fetchone()
        if row is None or row["role"] != WRITER_ROLE:
            conn.close()
            raise ConfigError(f"investigation persistence must connect as {WRITER_ROLE} (AI_WRITER_DATABASE_URL)")
        return conn

    def check(self) -> None:
        """Connects once; raises ConfigError for a wrong role and psycopg.Error when the database is unreachable."""
        with self._connect():
            pass

    def start_run(self, incident_id: str) -> StartResult:
        """Queues a run unless the incident is unknown or already has a queued/running one (serialized per incident)."""
        with self._connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%(incident_id)s))", {"incident_id": incident_id})
            created = conn.execute(CREATE_RUN_SQL, {"incident_id": incident_id}).fetchone()
            if created is not None:
                return StartResult("queued", created["id"])
            exists = conn.execute(INCIDENT_SQL, {"incident_id": incident_id}).fetchone()
            return StartResult("in_progress" if exists else "not_found")

    def mark_running(self, run_id: str, model: str, prompt_version: str) -> None:
        with self._connect() as conn:
            conn.execute(MARK_RUNNING_SQL, {"run_id": run_id, "model": model, "prompt_version": prompt_version})

    def load_incident(self, incident_id: str) -> IncidentContext | None:
        params = {"incident_id": incident_id}
        with self._connect() as conn:
            incident = conn.execute(INCIDENT_SQL, params).fetchone()
            if incident is None:
                return None
            events = conn.execute(INCIDENT_EVENTS_SQL, {**params, "limit": MAX_INCIDENT_EVENTS}).fetchall()
            alerts = conn.execute(INCIDENT_ALERTS_SQL, {**params, "limit": MAX_INCIDENT_ALERTS}).fetchall()
        return IncidentContext(
            incident=_utc(incident, "started_at", "updated_at"),
            events=[_utc(e, "occurred_at") for e in events],
            alerts=[dict(a) for a in alerts],
        )

    def add_evidence(self, run_id: str, items: list[tuple[SourceType, str, str, Any]]) -> list[str]:
        """Appends (source_type, source_id, claim, data) rows in one transaction; returns their `ev_` IDs in order."""
        ids: list[str] = []
        with self._connect() as conn:
            for source_type, source_id, claim, data in items:
                row = conn.execute(
                    INSERT_EVIDENCE_SQL,
                    {
                        "run_id": run_id,
                        "source_type": source_type,
                        "source_id": source_id,
                        "claim": claim,
                        "data": _jsonb(data),
                    },
                ).fetchone()
                if row is None:  # INSERT ... RETURNING always returns the row
                    raise RuntimeError("evidence insert returned no id")
                ids.append(row["id"])
        return ids

    def add_trace(
        self,
        run_id: str,
        step_index: int,
        action_type: str,
        *,
        origin: Origin | None = None,
        tool_name: str | None = None,
        input_json: Any = None,
        result_json: Any = None,
        evidence_ids: list[str] | None = None,
        retrieval_refs: list[str] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                INSERT_TRACE_SQL,
                {
                    "run_id": run_id,
                    "step_index": step_index,
                    "action_type": action_type,
                    "origin": origin,
                    "tool_name": tool_name,
                    "input": _jsonb(input_json),
                    "result": _jsonb(result_json),
                    "evidence_ids": _jsonb(evidence_ids or []),
                    "retrieval_refs": _jsonb(retrieval_refs or []),
                },
            )

    def finish_run(
        self,
        run_id: str,
        *,
        status: Literal["completed", "failed"],
        requires_review: bool,
        verdict: dict[str, Any] | None = None,
        raw_output: Any = None,
        validation_errors: list[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                FINISH_RUN_SQL,
                {
                    "run_id": run_id,
                    "status": status,
                    "requires_review": requires_review,
                    "verdict": _jsonb(verdict),
                    "raw_output": _jsonb(raw_output),
                    "validation_errors": _jsonb(validation_errors),
                    "error_message": error_message,
                },
            )

    def abandon_unfinished_runs(self) -> int:
        """At startup: runs left queued/running by a previous process can never finish (D-065)."""
        # ponytail: assumes a single AI service instance (D-023); several instances would need run ownership.
        with self._connect() as conn:
            cursor = conn.execute(ABANDON_RUNS_SQL, {"message": "abandoned: the AI service restarted mid-run"})
            return cursor.rowcount
