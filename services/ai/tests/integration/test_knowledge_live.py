"""Phase 09 exit: retrieval smoke tests with source IDs (D-070-D-072).

Real stack: Qdrant (Compose), all-MiniLM-L6-v2 on CPU, PostgreSQL (throwaway database). The corpus is ingested by
the conftest `knowledge` fixture exactly as `python -m sentinelx_ai.knowledge` does.
"""

from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb
from qdrant_client.models import PointStruct

from sentinelx_ai.knowledge import QdrantRetriever, ingest, load_corpus, qdrant_client
from sentinelx_ai.tools import ToolDatabase, ToolError, build_tools

from .conftest import Knowledge, Stack, owner_connect

pytestmark = pytest.mark.integration

# Query (no technique names, no document titles) -> source references any of which must rank in the top 3.
SMOKE_QUERIES = [
    ("many wrong passwords for one account and then the attacker got in", {"pb-brute-force-then-success", "T1110"}),
    ("powershell started with an encoded command in a hidden window", {"pb-encoded-powershell", "T1059.001"}),
    ("someone opened confidential payroll and HR spreadsheets on the file server", {"pb-sensitive-file-access"}),
    ("account added to the administrators group without a change ticket", {"pb-privilege-escalation", "T1548"}),
    ("the same user signed in from two countries an hour apart", {"pb-impossible-travel"}),
]


def retriever(knowledge: Knowledge) -> QdrantRetriever:
    return QdrantRetriever(lambda: qdrant_client(knowledge.qdrant_url, 5), knowledge.collection, knowledge.embedder)


def stored(owner_url: str) -> dict[str, tuple[str, str, str | None]]:
    with owner_connect(owner_url) as conn:
        rows = conn.execute("SELECT id, source, external_id, qdrant_point_id FROM knowledge_documents").fetchall()
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


def test_ingest_writes_one_row_and_one_point_per_document(database: Stack, knowledge: Knowledge) -> None:
    corpus = load_corpus()
    assert knowledge.counts.documents == len(corpus) and knowledge.counts.removed == 0
    rows = stored(database.owner_url)
    assert {(s, e) for s, e, _ in rows.values()} == {(d.source, d.external_id) for d in corpus}
    client = qdrant_client(knowledge.qdrant_url, 5)
    assert client.count(knowledge.collection, exact=True).count == len(corpus)
    points = client.retrieve(knowledge.collection, ids=[p for _, _, p in rows.values() if p], with_payload=True)
    assert {p.payload["document_id"] for p in points if p.payload} == set(rows)


@pytest.mark.parametrize(("query", "expected"), SMOKE_QUERIES)
def test_smoke_queries_return_the_expected_sources(
    database: Stack, knowledge: Knowledge, query: str, expected: set[str]
) -> None:
    hits = retriever(knowledge).search(query, 3, 5.0)
    assert len(hits) == 3
    assert {h.external_id for h in hits} & expected, [(h.external_id, round(h.score, 3)) for h in hits]
    rows = stored(database.owner_url)
    for hit in hits:  # every hit is a source reference to a stored document
        assert rows[hit.document_id][:2] == (hit.source, hit.external_id)


def test_the_agent_tool_returns_hits_with_source_ids_as_the_tools_role(database: Stack, knowledge: Knowledge) -> None:
    tools = {t.name: t for t in build_tools(ToolDatabase(database.tools_url), retriever(knowledge))}
    result = tools["search_security_knowledge"].invoke({"query": "login after repeated failures from a botnet IP"})
    assert 1 <= len(result["hits"]) <= 5
    rows = stored(database.owner_url)
    assert all(h["document_id"] in rows for h in result["hits"])
    assert {"pb-brute-force-then-success", "T1110", "pb-login-from-risky-ip"} & {
        h["external_id"] for h in result["hits"]
    }


def test_reingest_is_idempotent_and_removes_documents_no_longer_in_the_corpus(
    database: Stack, knowledge: Knowledge
) -> None:
    before = stored(database.owner_url)
    client = qdrant_client(knowledge.qdrant_url, 5)
    stale_point = "00000000-0000-0000-0000-00000000beef"
    with owner_connect(database.owner_url) as conn:
        stale = conn.execute(
            "INSERT INTO knowledge_documents (source, external_id, title, content_hash, qdrant_point_id, "
            "metadata_json) "
            "VALUES ('sentinelx-playbook', 'pb-retired', 'Retired', 'x', %s, %s) RETURNING id",
            (stale_point, Jsonb({})),
        ).fetchone()
    assert stale is not None
    client.upsert(
        knowledge.collection,
        points=[PointStruct(id=stale_point, vector=[0.05] * 384, payload={"document_id": stale[0]})],
        wait=True,
    )

    counts = ingest(database.owner_url, client, knowledge.collection, knowledge.embedder)
    assert counts.removed == 1
    assert stored(database.owner_url) == before  # same kd_ IDs and point IDs; the retired row is gone
    assert client.count(knowledge.collection, exact=True).count == len(load_corpus())


def test_unreachable_qdrant_or_missing_collection_is_a_typed_tool_error(database: Stack, knowledge: Knowledge) -> None:
    closed = QdrantRetriever(lambda: qdrant_client("http://127.0.0.1:1", 2), knowledge.collection, knowledge.embedder)
    missing = QdrantRetriever(lambda: qdrant_client(knowledge.qdrant_url, 2), "no_such_collection", knowledge.embedder)
    for broken in (closed, missing):
        tool = {t.name: t for t in build_tools(ToolDatabase(database.tools_url), broken)}["search_security_knowledge"]
        with pytest.raises(ToolError) as caught:
            tool.invoke({"query": "brute force"})
        assert caught.value.code == "unavailable"
