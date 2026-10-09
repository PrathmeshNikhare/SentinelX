"""Review path persisted in PostgreSQL (D-019, D-073): an ungrounded verdict is rejected and kept for audit.

Real Store (writer role), real tools (tools role), real database; the LLM is scripted to cite references that do
not exist, so the outcome is deterministic.
"""

from __future__ import annotations

from typing import Any

import pytest

from sentinelx_ai.graph import Deps, Investigator
from sentinelx_ai.store import Store
from sentinelx_ai.tools import ToolDatabase, build_tools

from ..test_graph import VERDICT, ScriptedLlm
from .conftest import Stack, owner_connect
from .test_investigation_live import insert_incident, run_row

pytestmark = pytest.mark.integration

UNGROUNDED = {**VERDICT, "evidence_ids": ["ev_ffffffffffffffff"], "mitre_techniques": ["T1003"]}


def investigate(database: Stack, verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    incident_id = insert_incident(database.owner_url, "Review path probe")
    store = Store(database.writer_url)
    started = store.start_run(incident_id)
    assert started.run_id
    tool_db = ToolDatabase(database.tools_url)
    tools = {t.name: t for t in build_tools(tool_db, None)}
    Investigator(Deps(store, ScriptedLlm(verdicts=verdicts), tools, tool_db)).run(started.run_id, incident_id)
    return {"id": started.run_id, **run_row(database.owner_url, started.run_id)}


def test_an_ungrounded_verdict_is_rejected_and_preserved_for_review(database: Stack) -> None:
    run = investigate(database, [UNGROUNDED, UNGROUNDED])
    assert run["status"] == "completed" and run["requires_review"] is True
    assert run["verdict_json"] is None
    attempts = run["raw_output_json"]["attempts"]
    assert [a["output"]["evidence_ids"] for a in attempts] == [["ev_ffffffffffffffff"]] * 2  # audit copy (D-019)
    assert {(e["attempt"], e["code"]) for e in run["validation_errors_json"]} == {
        (0, "unknown_evidence_id"),
        (0, "unknown_mitre_technique"),  # T1003 is outside the curated set (real mitre_techniques table)
        (1, "unknown_evidence_id"),
        (1, "unknown_mitre_technique"),
    }
    with owner_connect(database.owner_url) as conn:
        step = conn.execute(
            "SELECT result_json FROM investigation_trace WHERE investigation_run_id = %s "
            "AND action_type = 'validate_verdict'",
            (run["id"],),
        ).fetchone()
    assert step is not None and step[0]["accepted"] is False and step[0]["requires_review"] is True
