"""Phase 08 exit: the demo incident is investigated asynchronously with a schema-valid verdict and a full trace.

Real stack: the AI service under uvicorn, PostgreSQL (throwaway database; tools and writer roles), Ollama with the
configured model. The incident is scenario A shaped like the detection worker stores it (events, rule signals,
alerts, incident links); detection itself is tested in services/detection.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn
from psycopg.types.json import Jsonb

from sentinelx_ai.app import create_app
from sentinelx_ai.config import REPO_ROOT, ConfigError, Settings
from sentinelx_ai.contracts import Verdict
from sentinelx_ai.graph import MAX_STEPS, PROMPT_VERSION
from sentinelx_ai.knowledge import QdrantRetriever, qdrant_client
from sentinelx_ai.store import Store

from .conftest import Knowledge, Stack, owner_connect

pytestmark = pytest.mark.integration

TOKEN = "integration-service-token-0123456789-abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ANALYST = "an_00000000000000a1"
BASE = datetime(2026, 10, 8, 14, 0, tzinfo=UTC)
RUN_TIMEOUT_SECONDS = 600
# Rule hits per scenario-A event index, as the Phase 04 rules produce them (services/detection tests).
SIGNALS = {
    4: [("brute_force_attempts", 60)],
    5: [("login_after_failures", 75), ("risky_ip_login", 90)],
    6: [("suspicious_powershell", 85), ("post_compromise_chain", 85)],
    7: [("sensitive_file_access", 50), ("post_compromise_chain", 85)],
    8: [("sensitive_file_access", 50), ("post_compromise_chain", 85)],
}
ALERT_RISK = {5: 90, 6: 88, 7: 72, 8: 72}


def insert_incident(owner_url: str, title: str) -> str:
    events = json.loads((REPO_ROOT / "fixtures" / "scenarios" / "scenario-a.json").read_text(encoding="utf-8"))[
        "events"
    ]
    with owner_connect(owner_url) as conn:
        incident = conn.execute(
            "INSERT INTO incidents (title, risk_score, severity, primary_user_id, primary_ip, started_at) "
            "VALUES (%s, 90, 'CRITICAL', 'alice', '203.0.113.45', %s) RETURNING id",
            (title, BASE),
        ).fetchone()
        assert incident is not None
        for i, e in enumerate(events):
            row = conn.execute(
                "INSERT INTO security_events (external_event_id, occurred_at, user_id, source_ip, event_type, action, "
                "resource, status, metadata_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    f"{incident[0]}-{i}",
                    BASE + timedelta(seconds=e["offset_seconds"]),
                    e["user_id"],
                    e["source_ip"],
                    e["event_type"],
                    e["action"],
                    e["resource"],
                    e["status"],
                    Jsonb(e.get("metadata", {})),
                ),
            ).fetchone()
            assert row is not None
            conn.execute("INSERT INTO incident_events (incident_id, event_id) VALUES (%s, %s)", (incident[0], row[0]))
            for rule, score in SIGNALS.get(i, []):
                severity = "CRITICAL" if score >= 85 else "HIGH" if score >= 70 else "MEDIUM"
                conn.execute(
                    "INSERT INTO detection_signals (event_id, rule_name, rule_score, severity, reason) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (row[0], rule, score, severity, f"{rule} fired"),
                )
            if i in ALERT_RISK:
                reasons = {"signals": [{"rule": r, "score": s, "reason": f"{r} fired"} for r, s in SIGNALS[i]]}
                alert = conn.execute(
                    "INSERT INTO alerts (event_id, risk_score, anomaly_score, model_version, severity, reasons_json) "
                    "VALUES (%s, %s, 0.78, 'test', %s, %s) RETURNING id",
                    (row[0], ALERT_RISK[i], "CRITICAL" if ALERT_RISK[i] >= 85 else "HIGH", Jsonb(reasons)),
                ).fetchone()
                assert alert is not None
                conn.execute(
                    "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)", (incident[0], alert[0])
                )
    return str(incident[0])


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def service(database: Stack, knowledge: Knowledge) -> Iterator[str]:
    settings = Settings(
        service_token=TOKEN,
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434",
        ollama_model=os.environ.get("OLLAMA_MODEL") or "llama3.2:3b",
        ollama_timeout_seconds=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS") or 120),
        tools_database_url=database.tools_url,
        writer_database_url=database.writer_url,
        qdrant_api_key=knowledge.api_key,
        qdrant_url=knowledge.qdrant_url,
        knowledge_collection=knowledge.collection,
    )
    connect = lambda: qdrant_client(knowledge.qdrant_url, 5, knowledge.api_key)  # noqa: E731
    retriever = QdrantRetriever(connect, knowledge.collection, knowledge.embedder)  # model already loaded
    app = create_app(settings, retriever=retriever)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "the AI service did not start"
        time.sleep(0.1)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=30)


def run_row(owner_url: str, run_id: str) -> dict[str, Any]:
    with owner_connect(owner_url) as conn:
        cursor = conn.execute(
            "SELECT status::text, requires_review, verdict_json, raw_output_json, validation_errors_json, model_name, "
            "prompt_version, error_message FROM investigation_runs WHERE id = %s",
            (run_id,),
        )
        names = [d.name for d in cursor.description or []]
        row = cursor.fetchone()
    assert row is not None
    return dict(zip(names, row, strict=True))


def poll_run(owner_url: str, run_id: str) -> dict[str, Any]:
    """One status poll. A connection timeout of the test's own poll under memory pressure counts as "still running";
    the deadline still bounds the wait (seen once in Phase 13, D-080)."""
    try:
        return run_row(owner_url, run_id)
    except psycopg.OperationalError:
        return {"status": "running"}


def test_demo_incident_is_investigated_asynchronously_with_a_schema_valid_verdict(
    service: str, database: Stack
) -> None:
    incident_id = insert_incident(database.owner_url, "Possible account compromise: alice")
    request = {"incident_id": incident_id, "requested_by": ANALYST}

    started = time.monotonic()
    accepted = httpx.post(f"{service}/v1/investigations", json=request, headers=AUTH, timeout=10)
    assert accepted.status_code == 202, accepted.text
    assert time.monotonic() - started < 5  # answered before the graph runs
    run_id = accepted.json()["investigation_run_id"]
    assert run_row(database.owner_url, run_id)["status"] in ("queued", "running")
    duplicate = httpx.post(f"{service}/v1/investigations", json=request, headers=AUTH, timeout=10)
    assert duplicate.status_code == 409

    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    while (run := poll_run(database.owner_url, run_id))["status"] in ("queued", "running"):
        assert time.monotonic() < deadline, "the investigation did not finish"
        time.sleep(2)
    elapsed = time.monotonic() - started

    assert run["status"] == "completed", run["error_message"]
    assert run["requires_review"] is False, run["validation_errors_json"]
    verdict = Verdict.model_validate(run["verdict_json"])
    assert run["model_name"] and run["prompt_version"] == PROMPT_VERSION
    final = run["raw_output_json"]["attempts"][-1]
    assert final["valid"] is True and final["output"] == run["verdict_json"]

    with owner_connect(database.owner_url) as conn:
        trace = conn.execute(
            "SELECT step_index, action_type, action_origin::text, tool_name, result_json, evidence_ids_json "
            "FROM investigation_trace WHERE investigation_run_id = %s ORDER BY step_index",
            (run_id,),
        ).fetchall()
        evidence = dict(
            conn.execute(
                "SELECT id, source_type::text FROM evidence WHERE investigation_run_id = %s", (run_id,)
            ).fetchall()
        )
        supported = {  # D-073: found MITRE lookups and MITRE knowledge hits of this run
            row[0]
            for row in conn.execute(
                "SELECT CASE WHEN source_type = 'mitre' THEN source_id ELSE data_json->>'external_id' END "
                "FROM evidence WHERE investigation_run_id = %s "
                "AND ((source_type = 'mitre' AND (data_json->>'found')::boolean) "
                "OR (source_type = 'knowledge' AND data_json->>'source' = 'mitre-attack'))",
                (run_id,),
            ).fetchall()
        }
    assert [t[0] for t in trace] == list(range(len(trace)))
    assert trace[0][1] == "load_incident" and [t[1] for t in trace[-2:]] == ["build_verdict", "validate_verdict"]
    calls = [t for t in trace if t[1] == "tool_call"]
    assert 1 <= len(calls) <= MAX_STEPS
    assert all(t[2] in ("llm", "fallback") for t in trace if t[1] in ("choose_action", "tool_call"))
    assert {sid for t in trace for sid in t[5]} <= set(evidence)  # the trace only references stored evidence
    assert set(verdict.evidence_ids) <= set(evidence)  # grounded: every cited ID is this run's evidence
    assert set(verdict.mitre_techniques) <= supported
    assert list(evidence.values()).count("event") == 9 and list(evidence.values()).count("alert") == 4

    print(  # recorded in the Phase 08 handoff (pytest -s)
        json.dumps(
            {
                "seconds": round(elapsed, 1),
                "verdict": verdict.verdict,
                "severity": verdict.severity,
                "cited": len(verdict.evidence_ids),
                "cited_existing": len(set(verdict.evidence_ids) & set(evidence)),
                "mitre": verdict.mitre_techniques,
                "knowledge_evidence": list(evidence.values()).count("knowledge"),
                "attempts": len(run["raw_output_json"]["attempts"]),
                "findings": run["validation_errors_json"],
                "steps": [(t[1], t[2], t[3], (t[4] or {}).get("reason")) for t in trace],
            }
        )
    )


def test_persistence_refuses_any_role_but_the_writer(database: Stack) -> None:
    for url in (database.owner_url, database.app_url, database.tools_url):
        with pytest.raises(ConfigError, match="sentinelx_ai_writer"):
            Store(url).check()
    Store(database.writer_url).check()


def test_startup_abandons_runs_left_unfinished_by_a_previous_process(database: Stack) -> None:
    incident_id = insert_incident(database.owner_url, "Abandoned run probe")
    store = Store(database.writer_url)
    queued = store.start_run(incident_id)
    assert queued.outcome == "queued" and queued.run_id
    assert store.start_run(incident_id).outcome == "in_progress"
    assert store.start_run("inc_0000000000000000").outcome == "not_found"
    assert store.abandon_unfinished_runs() >= 1
    run = run_row(database.owner_url, queued.run_id)
    assert run["status"] == "failed" and run["error_message"] == "abandoned: the AI service restarted mid-run"
    assert store.start_run(incident_id).outcome == "queued"  # the incident can be investigated again
