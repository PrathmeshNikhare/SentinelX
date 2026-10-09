"""Agent tools without a database (docs/06, D-060-D-063): schemas, bounds, registry, error mapping, capabilities."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import psycopg
import pytest
from psycopg.rows import DictRow
from pydantic import ValidationError

from sentinelx_ai import tools
from sentinelx_ai.config import ConfigError, refuse_cloud_tracing
from sentinelx_ai.tools import (
    KNOWLEDGE_TIMEOUT_SECONDS,
    MAX_RESULT_BYTES,
    TOOL_NAMES,
    IpReputationInput,
    KnowledgeHit,
    KnowledgeSearchInput,
    MitreTechniqueInput,
    RelatedLogsInput,
    ToolDatabase,
    ToolError,
    UserHistoryInput,
    build_tools,
)

END = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)
START = END - timedelta(hours=1)
WINDOW = {"start_time": START.isoformat(), "end_time": END.isoformat()}


class FakeDb(ToolDatabase):
    """Records every query; returns canned rows. No connection is ever opened."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        super().__init__("postgresql://unused.invalid/none")
        self.rows = rows or []
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def fetch(self, tool: str, query: str, params: dict[str, Any]) -> list[DictRow]:
        self.calls.append((tool, query, params))
        return [dict(r) for r in self.rows]


class FakeRetriever:
    def __init__(self, hits: Sequence[KnowledgeHit] = (), error: Exception | None = None) -> None:
        self.hits, self.error = list(hits), error
        self.calls: list[tuple[str, int, float]] = []

    def search(self, query: str, top_k: int, timeout_seconds: float) -> Sequence[KnowledgeHit]:
        self.calls.append((query, top_k, timeout_seconds))
        if self.error:
            raise self.error
        return self.hits


def hit(n: int) -> KnowledgeHit:
    return KnowledgeHit(
        document_id=f"kd_{n:016x}", source="mitre", title=f"Doc {n}", snippet="Brute force guidance.", score=0.9
    )


def event_row(n: int, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "event_id": f"se_{n:016x}",
        "external_event_id": f"demo-{n}",
        "occurred_at": END.astimezone(timezone(timedelta(hours=5, minutes=30))) - timedelta(minutes=n),
        "user_id": "alice",
        "source_ip": "203.0.113.45",
        "event_type": "authentication",
        "action": "login",
        "resource": "vpn",
        "status": "failed",
        "metadata": metadata or {},
    }


def by_name(db: ToolDatabase, retriever: FakeRetriever | None = None) -> dict[str, Any]:
    return {t.name: t for t in build_tools(db, retriever or FakeRetriever())}


# --- registry --------------------------------------------------------------------------------------------------------


def test_registry_is_exactly_the_five_read_only_tools() -> None:
    registry = build_tools(FakeDb(), FakeRetriever())
    assert tuple(t.name for t in registry) == TOOL_NAMES
    assert set(TOOL_NAMES) == {
        "get_user_history",
        "get_ip_reputation",
        "get_related_logs",
        "get_mitre_technique",
        "search_security_knowledge",
    }
    for tool in registry:
        assert tool.metadata is not None and tool.metadata["read_only"] is True
        assert 0 < tool.metadata["timeout_seconds"] <= 15
        assert tool.metadata["max_result_bytes"] == MAX_RESULT_BYTES
        schema = tool.args_schema.model_json_schema()  # type: ignore[union-attr]
        assert schema["additionalProperties"] is False, tool.name
        assert tool.description
        assert tool.args_schema is tools.TOOL_INPUTS[tool.name]


def test_knowledge_search_is_not_offered_without_a_retriever() -> None:
    assert [t.name for t in build_tools(FakeDb(), None)] == [n for n in TOOL_NAMES if n != "search_security_knowledge"]


# --- input bounds ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"user_id": "alice' OR '1'='1"},  # SQL injection never reaches a query: the schema rejects it
        {"user_id": "Alice"},
        {"user_id": ""},
        {"limit": 0},
        {"limit": 51},
        {"start_time": END.isoformat()},  # empty window
        {"start_time": (END - timedelta(days=7, seconds=1)).isoformat()},  # window over 7 days
        {"start_time": "2026-10-08T14:00:00"},  # naive timestamp
        {"query": "SELECT * FROM analysts"},  # unknown field
    ],
)
def test_user_history_rejects_out_of_bounds_input(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        UserHistoryInput.model_validate({"user_id": "alice", **WINDOW, **overrides})


def test_user_history_accepts_the_maximum_window_and_normalizes_timezones() -> None:
    args = UserHistoryInput.model_validate(
        {"user_id": "alice", "start_time": "2026-10-01T20:30:00+05:30", "end_time": "2026-10-08T15:00:00Z"}
    )
    assert args.end_time - args.start_time == timedelta(days=7)
    assert args.limit == 20


@pytest.mark.parametrize(
    "payload",
    [
        {**WINDOW},  # neither user_id nor source_ip
        {**WINDOW, "source_ip": "999.1.1.1"},
        {**WINDOW, "source_ip": "10.0.0.1; DROP TABLE security_events"},
        {**WINDOW, "user_id": "alice", "event_types": []},
        {**WINDOW, "user_id": "alice", "event_types": ["authentication", "authentication"]},
        {**WINDOW, "user_id": "alice", "event_types": ["shell"]},
    ],
)
def test_related_logs_rejects_untargeted_or_malformed_input(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RelatedLogsInput.model_validate(payload)


@pytest.mark.parametrize("ip", ["", "10.0.0", "localhost", "10.0.0.1/8", "203.0.113.45' --"])
def test_ip_reputation_rejects_non_addresses(ip: str) -> None:
    with pytest.raises(ValidationError):
        IpReputationInput.model_validate({"ip": ip})


@pytest.mark.parametrize("technique_id", ["T110", "t1110", "T1110.1", "T1110'; --", "TA0001"])
def test_mitre_technique_rejects_malformed_ids(technique_id: str) -> None:
    with pytest.raises(ValidationError):
        MitreTechniqueInput.model_validate({"technique_id": technique_id})


@pytest.mark.parametrize(
    "payload", [{"query": "ab"}, {"query": "x" * 501}, {"query": "line\nbreak"}, {"query": "brute", "top_k": 11}]
)
def test_knowledge_search_rejects_out_of_bounds_input(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchInput.model_validate(payload)


def test_invalid_tool_arguments_never_reach_the_database() -> None:
    db = FakeDb()
    registry = by_name(db)
    with pytest.raises(ValidationError):
        registry["get_user_history"].invoke({"user_id": "alice; DROP TABLE x", **WINDOW})
    with pytest.raises(ValidationError):
        registry["get_mitre_technique"].invoke({"technique_id": "T1110", "sql": "DELETE FROM incidents"})
    assert db.calls == []


# --- results ---------------------------------------------------------------------------------------------------------


def test_user_history_passes_bounds_as_parameters_and_reports_truncation() -> None:
    db = FakeDb([event_row(1), event_row(2), event_row(3)])
    result = by_name(db)["get_user_history"].invoke({"user_id": "alice", **WINDOW, "limit": 2})
    (tool, query, params), *_ = db.calls
    assert tool == "get_user_history" and query is tools.EVENTS_SQL
    assert params == {
        "start": START,
        "end": END,
        "user_id": "alice",
        "source_ip": None,
        "event_types": None,
        "fetch": 3,
    }
    assert [e["event_id"] for e in result["events"]] == ["se_0000000000000001", "se_0000000000000002"]
    assert result["truncated"] is True
    assert result["events"][0]["occurred_at"] == "2026-10-08T14:59:00Z"  # converted to UTC


def test_related_logs_filters_are_parameters() -> None:
    db = FakeDb()
    result = by_name(db)["get_related_logs"].invoke(
        {**WINDOW, "source_ip": "2001:db8::1", "event_types": ["authentication", "process"]}
    )
    assert result == {"events": [], "truncated": False}
    params = db.calls[0][2]
    assert params["user_id"] is None and params["source_ip"] == "2001:db8::1"
    assert params["event_types"] == ["authentication", "process"]


def test_event_results_are_cut_to_the_byte_budget() -> None:
    bulky = {f"k{i}": "x" * 60 for i in range(60)}  # about 4 KB, the event contract's metadata ceiling
    db = FakeDb([event_row(n, bulky) for n in range(1, 51)])
    result = by_name(db)["get_user_history"].invoke({"user_id": "alice", **WINDOW, "limit": 50})
    assert result["truncated"] is True
    assert 1 <= len(result["events"]) < 50
    assert len(tools.EventsResult.model_validate(result).model_dump_json()) <= MAX_RESULT_BYTES


def test_unknown_ip_and_technique_return_typed_not_found_results() -> None:
    registry = by_name(FakeDb())
    assert registry["get_ip_reputation"].invoke({"ip": "10.99.99.99"}) == {
        "ip": "10.99.99.99",
        "known": False,
        "reputation": "unknown",
        "score": None,
        "tags": [],
        "source": None,
    }
    assert registry["get_mitre_technique"].invoke({"technique_id": "T9999"}) == {
        "technique_id": "T9999",
        "found": False,
        "name": None,
        "tactics": [],
        "description": None,
        "attack_version": None,
    }


def test_known_ip_and_technique_rows_are_mapped() -> None:
    ip_row = {"reputation": "malicious", "score": 95, "tags": ["tor-exit"], "source": "fixture"}
    assert by_name(FakeDb([ip_row]))["get_ip_reputation"].invoke({"ip": "203.0.113.45"})["known"] is True
    technique = {
        "technique_id": "T1110",
        "name": "Brute Force",
        "tactics": ["credential-access"],
        "description": "Repeated authentication attempts.",
        "attack_version": "17.1",
    }
    result = by_name(FakeDb([technique]))["get_mitre_technique"].invoke({"technique_id": "T1110"})
    assert result == {**technique, "found": True}


def test_knowledge_search_passes_the_timeout_and_caps_hits() -> None:
    retriever = FakeRetriever([hit(n) for n in range(1, 8)])
    result = by_name(FakeDb(), retriever)["search_security_knowledge"].invoke({"query": "brute force", "top_k": 3})
    assert retriever.calls == [("brute force", 3, KNOWLEDGE_TIMEOUT_SECONDS)]
    assert [h["document_id"] for h in result["hits"]] == [f"kd_{n:016x}" for n in (1, 2, 3)]
    assert result["truncated"] is True


@pytest.mark.parametrize(("error", "code"), [(TimeoutError(), "timeout"), (ConnectionError(), "unavailable")])
def test_knowledge_search_maps_retriever_failures(error: Exception, code: str) -> None:
    tool = by_name(FakeDb(), FakeRetriever(error=error))["search_security_knowledge"]
    with pytest.raises(ToolError) as caught:
        tool.invoke({"query": "brute force"})
    assert caught.value.code == code


def test_knowledge_hits_must_cite_knowledge_document_ids() -> None:
    with pytest.raises(ValidationError):
        KnowledgeHit(document_id="ev_0000000000000001", source="mitre", title="t", snippet="s", score=0.5)
    with pytest.raises(ValidationError):
        KnowledgeHit(document_id="kd_0000000000000001", source="mitre", title="t", snippet="s", score=float("nan"))


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (psycopg.errors.QueryCanceled("canceling statement"), "timeout"),
        (psycopg.OperationalError("down"), "unavailable"),
    ],
)
def test_database_failures_become_tool_errors_without_details(
    monkeypatch: pytest.MonkeyPatch, error: Exception, code: str
) -> None:
    def fail(_url: str) -> None:
        raise error

    monkeypatch.setattr(tools, "connect_tools", fail)
    with pytest.raises(ToolError) as caught:
        ToolDatabase("postgresql://unused.invalid/none").fetch("get_ip_reputation", tools.IP_REPUTATION_SQL, {})
    assert caught.value.code == code
    assert "SELECT" not in str(caught.value) and "canceling" not in str(caught.value)


# --- forbidden capabilities (docs/06) --------------------------------------------------------------------------------

ALLOWED_IMPORTS = {
    "__future__",
    "collections.abc",
    "datetime",
    "typing",
    "urllib.parse",
    "psycopg",
    "psycopg.rows",
    "langchain_core.tools",
    "pydantic",
    "config",  # relative: .config
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "__import__", "getattr_static", "system", "popen"}


def test_tools_module_has_no_shell_file_network_or_dynamic_sql_capability() -> None:
    tree = ast.parse(inspect.getsource(tools))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    assert imported <= ALLOWED_IMPORTS, imported - ALLOWED_IMPORTS

    calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
    }
    assert not calls & FORBIDDEN_CALLS

    queries = {name: getattr(tools, name) for name in dir(tools) if name.endswith("_SQL")}
    assert set(queries) == {"EVENTS_SQL", "IP_REPUTATION_SQL", "MITRE_TECHNIQUE_SQL"}
    for name, text in queries.items():
        assert text.strip().upper().startswith("SELECT"), name
        assert ";" not in text and "{" not in text, name  # one statement, no format placeholders

    # Every execute() runs a module constant, a fixed literal or the caller-supplied fixed query: never built SQL.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            first = node.args[0]
            assert isinstance(first, ast.Name) or (isinstance(first, ast.Constant) and isinstance(first.value, str))


# --- configuration ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"])
def test_cloud_tracing_is_refused(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "true")
    with pytest.raises(ConfigError, match=name):
        refuse_cloud_tracing()


def test_tracing_off_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
        monkeypatch.setenv(name, "false")
    refuse_cloud_tracing()
