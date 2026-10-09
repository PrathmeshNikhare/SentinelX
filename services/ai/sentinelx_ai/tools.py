"""Typed read-only investigation tools (docs/06, D-060-D-063).

Database tools connect only as the SELECT-only role `sentinelx_ai_tools`, in read-only sessions with a statement
timeout, and run fixed parameterized queries. Nothing here writes, shells out, opens files or calls the network other
than PostgreSQL; knowledge search goes through the `KnowledgeRetriever` interface (fake in Phase 07, Qdrant in
Phase 09, D-026).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final, Literal, Protocol

import psycopg
from langchain_core.tools import StructuredTool
from psycopg.rows import DictRow, dict_row
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress, model_validator

from .config import PG_CONNECT_TIMEOUT_SECONDS, ConfigError, pg_connect_options

TOOLS_ROLE: Final = "sentinelx_ai_tools"
STATEMENT_TIMEOUT_MS: Final = 2000
KNOWLEDGE_TIMEOUT_SECONDS: Final = 5.0
MAX_WINDOW: Final = timedelta(days=7)
MAX_ROWS: Final = 50
DEFAULT_ROWS: Final = 20
MAX_TOP_K: Final = 10
MAX_RESULT_BYTES: Final = 32 * 1024

UserId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.@-]{0,127}$")]  # normalized-event contract
EventType = Literal["authentication", "process", "file_access", "privilege_change", "network"]
TechniqueId = Annotated[str, Field(pattern=r"^T[0-9]{4}(\.[0-9]{3})?$")]
Reputation = Literal["known_good", "unknown", "suspicious", "malicious"]
ErrorCode = Literal["timeout", "unavailable", "oversized"]


class ToolError(RuntimeError):
    """A tool could not answer. The message never carries SQL, parameters or row data."""

    def __init__(self, tool: str, code: ErrorCode, detail: str) -> None:
        super().__init__(f"{tool}: {code} ({detail})")
        self.tool = tool
        self.code = code


# ---------------------------------------------------------------------------------------------------------------------
# Input and output schemas. Inputs forbid unknown fields; every list and window is bounded.


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Window(ToolInput):
    start_time: AwareDatetime
    end_time: AwareDatetime
    limit: int = Field(DEFAULT_ROWS, ge=1, le=MAX_ROWS)

    @model_validator(mode="after")
    def _bounded(self) -> _Window:
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        if self.end_time - self.start_time > MAX_WINDOW:
            raise ValueError(f"the time window must be at most {MAX_WINDOW.days} days")
        return self


class UserHistoryInput(_Window):
    user_id: UserId


class RelatedLogsInput(_Window):
    user_id: UserId | None = None
    source_ip: IPvAnyAddress | None = None
    event_types: list[EventType] | None = Field(None, min_length=1, max_length=5)

    @model_validator(mode="after")
    def _targeted(self) -> RelatedLogsInput:
        if self.user_id is None and self.source_ip is None:
            raise ValueError("at least one of user_id or source_ip is required")
        if self.event_types is not None and len(set(self.event_types)) != len(self.event_types):
            raise ValueError("event_types must be unique")
        return self


class IpReputationInput(ToolInput):
    ip: IPvAnyAddress


class MitreTechniqueInput(ToolInput):
    technique_id: TechniqueId


class KnowledgeSearchInput(ToolInput):
    query: str = Field(min_length=3, max_length=500, pattern=r"^[^\x00-\x1f\x7f]+$")
    top_k: int = Field(5, ge=1, le=MAX_TOP_K)


class EventRecord(ToolOutput):
    event_id: str  # security_events.id (se_…), the persisted event the verdict can cite through evidence
    external_event_id: str
    occurred_at: datetime
    user_id: str
    source_ip: str
    event_type: str
    action: str
    resource: str
    status: str
    metadata: dict[str, Any]


class EventsResult(ToolOutput):
    events: list[EventRecord]  # newest first
    truncated: bool  # more rows matched than returned (row limit or MAX_RESULT_BYTES)


class IpReputationResult(ToolOutput):
    ip: str
    known: bool
    reputation: Reputation
    score: int | None
    tags: list[str]
    source: str | None


class MitreTechniqueResult(ToolOutput):
    technique_id: str
    found: bool
    name: str | None = None
    tactics: list[str] = []
    description: str | None = None
    attack_version: str | None = None


class KnowledgeHit(ToolOutput):
    document_id: Annotated[str, Field(pattern=r"^kd_[0-9a-f]{16}$")]  # knowledge_documents.id (D-018, D-030)
    source: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=128)  # source reference, e.g. T1110 or a playbook slug
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(min_length=1, max_length=1500)
    score: float = Field(allow_inf_nan=False)


class KnowledgeResult(ToolOutput):
    hits: list[KnowledgeHit]  # best first
    truncated: bool


class KnowledgeRetriever(Protocol):
    """Semantic search over approved security knowledge (Qdrant in Phase 09).

    Implementations honor `timeout_seconds`, raise `TimeoutError` when it passes and `ConnectionError` when the store
    is unreachable, and return at most `top_k` hits, best first.
    """

    def search(self, query: str, top_k: int, timeout_seconds: float) -> Sequence[KnowledgeHit]: ...


# ---------------------------------------------------------------------------------------------------------------------
# Database access: SELECT-only role, read-only session, fixed queries.

EVENTS_SQL: Final = """
SELECT id AS event_id, external_event_id, occurred_at, user_id, host(source_ip) AS source_ip,
       event_type, action, resource, status, metadata_json AS metadata
FROM security_events
WHERE occurred_at >= %(start)s AND occurred_at < %(end)s
  AND (%(user_id)s::text IS NULL OR user_id = %(user_id)s::text)
  AND (%(source_ip)s::inet IS NULL OR source_ip = %(source_ip)s::inet)
  AND (%(event_types)s::text[] IS NULL OR event_type = ANY(%(event_types)s::text[]))
ORDER BY occurred_at DESC, id
LIMIT %(fetch)s
"""

IP_REPUTATION_SQL: Final = """
SELECT reputation::text AS reputation, score, tags_json AS tags, source
FROM ip_reputation WHERE ip = %(ip)s::inet
"""

MITRE_TECHNIQUE_SQL: Final = """
SELECT technique_id, name, tactics_json AS tactics, description, attack_version
FROM mitre_techniques WHERE technique_id = %(technique_id)s
"""

KNOWLEDGE_DOCUMENTS_SQL: Final = """
SELECT id FROM knowledge_documents WHERE id = ANY(%(ids)s::text[])
"""


def connect_tools(url: str) -> psycopg.Connection[DictRow]:
    """Read-only session as `sentinelx_ai_tools`; refuses any other role (D-061).

    Grants are the enforcement (D-031); the read-only default is defense in depth. IPv4 for `localhost` (D-051).
    """
    session = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS} -c TimeZone=UTC"
    conn = psycopg.connect(url, autocommit=True, row_factory=dict_row, **pg_connect_options(url, session))
    row = conn.execute("SELECT current_user AS role").fetchone()
    if row is None or row["role"] != TOOLS_ROLE:
        conn.close()
        raise ConfigError(f"agent tools must connect as {TOOLS_ROLE} (AI_TOOLS_DATABASE_URL)")
    return conn


class ToolDatabase:
    """One short-lived connection per call: tools run from background tasks (Phase 08) and share no state."""

    def __init__(self, url: str) -> None:
        self._url = url

    def fetch(self, tool: str, query: str, params: dict[str, Any]) -> list[DictRow]:
        try:
            with connect_tools(self._url) as conn:
                return conn.execute(query, params).fetchall()
        except psycopg.errors.QueryCanceled as error:
            raise ToolError(tool, "timeout", f"query exceeded {STATEMENT_TIMEOUT_MS} ms") from error
        except psycopg.Error as error:
            raise ToolError(tool, "unavailable", type(error).__name__) from error


# ---------------------------------------------------------------------------------------------------------------------
# Tool implementations.


def _fit[R: (EventsResult, KnowledgeResult)](result: R, field: str) -> R:
    """Drops trailing items until the serialized result fits MAX_RESULT_BYTES, marking it truncated."""
    items = list(getattr(result, field))
    while items and len(result.model_dump_json()) > MAX_RESULT_BYTES:
        items.pop()
        result = result.model_copy(update={field: items, "truncated": True})
    return result


def _events(db: ToolDatabase, tool: str, args: UserHistoryInput | RelatedLogsInput) -> EventsResult:
    source_ip = getattr(args, "source_ip", None)
    rows = db.fetch(
        tool,
        EVENTS_SQL,
        {
            "start": args.start_time,
            "end": args.end_time,
            "user_id": args.user_id,
            "source_ip": None if source_ip is None else str(source_ip),
            "event_types": getattr(args, "event_types", None),
            "fetch": args.limit + 1,  # one extra row tells us whether more matched
        },
    )
    events = [EventRecord.model_validate({**row, "occurred_at": row["occurred_at"].astimezone(UTC)}) for row in rows]
    return _fit(EventsResult(events=events[: args.limit], truncated=len(events) > args.limit), "events")


def get_user_history(db: ToolDatabase, args: UserHistoryInput) -> EventsResult:
    return _events(db, "get_user_history", args)


def get_related_logs(db: ToolDatabase, args: RelatedLogsInput) -> EventsResult:
    return _events(db, "get_related_logs", args)


def get_ip_reputation(db: ToolDatabase, args: IpReputationInput) -> IpReputationResult:
    ip = str(args.ip)
    rows = db.fetch("get_ip_reputation", IP_REPUTATION_SQL, {"ip": ip})
    if not rows:
        return IpReputationResult(ip=ip, known=False, reputation="unknown", score=None, tags=[], source=None)
    return IpReputationResult.model_validate({**rows[0], "ip": ip, "known": True})


def get_mitre_technique(db: ToolDatabase, args: MitreTechniqueInput) -> MitreTechniqueResult:
    rows = db.fetch("get_mitre_technique", MITRE_TECHNIQUE_SQL, {"technique_id": args.technique_id})
    if not rows:
        return MitreTechniqueResult(technique_id=args.technique_id, found=False)
    return MitreTechniqueResult.model_validate({**rows[0], "found": True})


def search_security_knowledge(
    db: ToolDatabase, retriever: KnowledgeRetriever, args: KnowledgeSearchInput
) -> KnowledgeResult:
    """Hits whose document is not in `knowledge_documents` are dropped: every result is a real source (D-072)."""
    tool = "search_security_knowledge"
    try:
        hits = list(retriever.search(args.query, args.top_k, KNOWLEDGE_TIMEOUT_SECONDS))
    except TimeoutError as error:
        raise ToolError(tool, "timeout", f"retrieval exceeded {KNOWLEDGE_TIMEOUT_SECONDS} s") from error
    except ConnectionError as error:
        raise ToolError(tool, "unavailable", str(error) or type(error).__name__) from error
    truncated, hits = len(hits) > args.top_k, hits[: args.top_k]
    known = {row["id"] for row in db.fetch(tool, KNOWLEDGE_DOCUMENTS_SQL, {"ids": [h.document_id for h in hits]})}
    return _fit(KnowledgeResult(hits=[h for h in hits if h.document_id in known], truncated=truncated), "hits")


# ---------------------------------------------------------------------------------------------------------------------
# LangChain registry (D-060). The agent sees exactly these five tools and nothing else.

TOOL_NAMES: Final = (
    "get_user_history",
    "get_ip_reputation",
    "get_related_logs",
    "get_mitre_technique",
    "search_security_knowledge",
)
TOOL_INPUTS: Final[dict[str, type[ToolInput]]] = {
    "get_user_history": UserHistoryInput,
    "get_ip_reputation": IpReputationInput,
    "get_related_logs": RelatedLogsInput,
    "get_mitre_technique": MitreTechniqueInput,
    "search_security_knowledge": KnowledgeSearchInput,
}


def _tool[In: ToolInput](
    name: str, description: str, schema: type[In], run: Callable[[In], ToolOutput], timeout_seconds: float
) -> StructuredTool:
    def call(**kwargs: Any) -> dict[str, Any]:
        result = run(schema.model_validate(kwargs))  # re-validate: StructuredTool passes only the given keys
        if len(result.model_dump_json()) > MAX_RESULT_BYTES:
            raise ToolError(name, "oversized", f"result exceeds {MAX_RESULT_BYTES} bytes")
        return result.model_dump(mode="json")

    return StructuredTool.from_function(
        func=call,
        name=name,
        description=description,
        args_schema=schema,
        metadata={"read_only": True, "timeout_seconds": timeout_seconds, "max_result_bytes": MAX_RESULT_BYTES},
    )


def build_tools(db: ToolDatabase, retriever: KnowledgeRetriever | None) -> list[StructuredTool]:
    """Usage: `build_tools(ToolDatabase(AI_TOOLS_DATABASE_URL), retriever)`.

    Without a retriever (until Phase 09 supplies Qdrant) knowledge search is not offered at all (D-067).
    """
    db_timeout = PG_CONNECT_TIMEOUT_SECONDS + STATEMENT_TIMEOUT_MS / 1000
    window = f"Window at most {MAX_WINDOW.days} days; limit 1-{MAX_ROWS} (default {DEFAULT_ROWS}); newest first."
    database_tools = [
        _tool(
            "get_user_history",
            f"Security events for one monitored user between start_time and end_time (UTC). {window}",
            UserHistoryInput,
            lambda a: get_user_history(db, a),
            db_timeout,
        ),
        _tool(
            "get_ip_reputation",
            "Local reputation of an IP address. Unknown addresses return reputation 'unknown'. No external lookups.",
            IpReputationInput,
            lambda a: get_ip_reputation(db, a),
            db_timeout,
        ),
        _tool(
            "get_related_logs",
            f"Security events by user_id and/or source_ip (at least one), optionally filtered by event_types. {window}",
            RelatedLogsInput,
            lambda a: get_related_logs(db, a),
            db_timeout,
        ),
        _tool(
            "get_mitre_technique",
            "A MITRE ATT&CK technique from the curated local set by ID (e.g. T1110). Unknown IDs return found=false.",
            MitreTechniqueInput,
            lambda a: get_mitre_technique(db, a),
            db_timeout,
        ),
    ]
    if retriever is None:
        return database_tools
    knowledge = _tool(
        "search_security_knowledge",
        f"Semantic search over approved security knowledge. top_k 1-{MAX_TOP_K}. Hits carry document IDs.",
        KnowledgeSearchInput,
        lambda a: search_security_knowledge(db, retriever, a),
        KNOWLEDGE_TIMEOUT_SECONDS,
    )
    return [*database_tools, knowledge]
