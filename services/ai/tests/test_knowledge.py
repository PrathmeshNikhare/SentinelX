"""Knowledge corpus and Qdrant retriever without servers or the real model (D-070-D-072).

Qdrant runs in its in-memory local mode; a hashing bag-of-words embedder stands in for sentence-transformers.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams

from sentinelx_ai import knowledge
from sentinelx_ai.knowledge import (
    EMBEDDING_DIMENSION,
    FIXTURES,
    MAX_TEXT_CHARS,
    Document,
    QdrantRetriever,
    ensure_collection,
    load_corpus,
)

COLLECTION = "test_knowledge"


class HashEmbedder:
    """Deterministic: each word adds weight to one of 384 buckets; vectors are normalized like the real model's."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise OSError("model files missing")
        vectors = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIMENSION
            for word in text.lower().split():
                vector[int(hashlib.sha256(word.strip(".,:;()").encode()).hexdigest(), 16) % EMBEDDING_DIMENSION] += 1
            norm = math.sqrt(sum(x * x for x in vector)) or 1.0
            vectors.append([x / norm for x in vector])
        return vectors


def indexed(client: QdrantClient, documents: list[Document], embedder: HashEmbedder) -> None:
    """What `ingest` writes to Qdrant, with fake `kd_` IDs instead of database rows."""
    ensure_collection(client, COLLECTION)
    vectors = embedder.encode([f"{d.title}. {d.text}" for d in documents])
    client.upsert(
        COLLECTION,
        points=[
            PointStruct(
                id=d.point_id,
                vector=v,
                payload={
                    "document_id": f"kd_{n:016x}",
                    "source": d.source,
                    "external_id": d.external_id,
                    "title": d.title,
                    "text": d.text,
                },
            )
            for n, (d, v) in enumerate(zip(documents, vectors, strict=True))
        ],
    )


@pytest.fixture
def memory() -> QdrantClient:
    return QdrantClient(":memory:")


# --- corpus ----------------------------------------------------------------------------------------------------------


def test_corpus_is_the_curated_mitre_set_plus_playbooks_with_unique_stable_ids() -> None:
    corpus = load_corpus()
    mitre = json.loads((FIXTURES / "mitre_techniques.json").read_text(encoding="utf-8"))["techniques"]
    by_source: dict[str, list[Document]] = {}
    for d in corpus:
        by_source.setdefault(d.source, []).append(d)
    assert [d.external_id for d in by_source["mitre-attack"]] == [t["technique_id"] for t in mitre]
    assert len(by_source["sentinelx-playbook"]) == 8
    assert len({d.point_id for d in corpus}) == len(corpus)
    assert all(1 <= len(d.text) <= MAX_TEXT_CHARS for d in corpus)
    assert load_corpus()[0].point_id == corpus[0].point_id  # deterministic across runs


def test_playbooks_only_reference_curated_techniques() -> None:
    curated = {d.external_id for d in load_corpus() if d.source == "mitre-attack"}
    for d in load_corpus():
        if d.source == "sentinelx-playbook":
            assert set(d.metadata["techniques"]) <= curated, d.external_id


def test_content_hash_tracks_text_and_model() -> None:
    a = Document("s", "x", "Title", "text")
    assert a.content_hash == Document("s", "x", "Title", "text").content_hash
    assert a.content_hash != Document("s", "x", "Title", "other text").content_hash


def test_oversized_or_duplicate_documents_are_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "mitre_techniques.json").write_text(
        json.dumps({"attack_version": "17.1", "techniques": []}), encoding="utf-8"
    )
    playbook = {"external_id": "pb-x", "title": "X", "techniques": [], "text": "x" * (MAX_TEXT_CHARS + 1)}
    (tmp_path / "knowledge" / "playbooks.json").write_text(
        json.dumps({"source": "p", "documents": [playbook]}), encoding="utf-8"
    )
    monkeypatch.setattr(knowledge, "FIXTURES", tmp_path)
    with pytest.raises(ValueError, match="characters"):
        load_corpus()
    playbook["text"] = "fine"
    (tmp_path / "knowledge" / "playbooks.json").write_text(
        json.dumps({"source": "p", "documents": [playbook, playbook]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_corpus()


# --- retrieval -------------------------------------------------------------------------------------------------------


def test_hits_carry_source_references_best_first(memory: QdrantClient) -> None:
    embedder = HashEmbedder()
    indexed(memory, load_corpus(), embedder)
    hits = QdrantRetriever(lambda: memory, COLLECTION, embedder).search(
        "PowerShell -EncodedCommand hidden window execution", 3, 5.0
    )
    assert len(hits) == 3
    assert hits[0].external_id in {"T1059.001", "pb-encoded-powershell"}
    assert all(h.document_id.startswith("kd_") and h.source and h.title and h.snippet for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_points_without_a_valid_source_reference_are_never_returned(memory: QdrantClient) -> None:
    embedder = HashEmbedder()
    ensure_collection(memory, COLLECTION)
    vector = embedder.encode(["brute force"])[0]
    memory.upsert(
        COLLECTION,
        points=[
            PointStruct(id=1, vector=vector, payload={"document_id": "not-a-kd-id", "source": "x", "title": "t"}),
            PointStruct(id=2, vector=vector, payload={}),
        ],
    )
    assert QdrantRetriever(lambda: memory, COLLECTION, embedder).search("brute force", 5, 5.0) == []


def test_ensure_collection_recreates_a_collection_with_the_wrong_vector_size(memory: QdrantClient) -> None:
    memory.create_collection(COLLECTION, vectors_config=VectorParams(size=8, distance=Distance.COSINE))
    ensure_collection(memory, COLLECTION)
    params = memory.get_collection(COLLECTION).config.params.vectors
    assert isinstance(params, VectorParams) and params.size == EMBEDDING_DIMENSION


class FailingClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def query_points(self, *args: Any, **kwargs: Any) -> Any:
        raise self.error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ResponseHandlingException(httpx.ReadTimeout("slow")), TimeoutError),
        (ResponseHandlingException(httpx.ConnectError("refused")), ConnectionError),
        (UnexpectedResponse(404, "Not Found", b"{}", httpx.Headers()), ConnectionError),
    ],
)
def test_qdrant_failures_map_to_the_retriever_contract(error: Exception, expected: type[Exception]) -> None:
    retriever = QdrantRetriever(lambda: FailingClient(error), COLLECTION, HashEmbedder())  # type: ignore[arg-type,return-value]
    with pytest.raises(expected):
        retriever.search("brute force", 3, 5.0)


def test_a_missing_embedding_model_makes_retrieval_unavailable(memory: QdrantClient) -> None:
    with pytest.raises(ConnectionError, match="embedding model unavailable"):
        QdrantRetriever(lambda: memory, COLLECTION, HashEmbedder(fail=True)).search("brute force", 3, 5.0)


def test_the_client_is_created_on_first_search_only() -> None:
    created: list[QdrantClient] = []

    def connect() -> QdrantClient:
        created.append(QdrantClient(":memory:"))
        indexed(created[-1], load_corpus()[:2], HashEmbedder())
        return created[-1]

    retriever = QdrantRetriever(connect, COLLECTION, HashEmbedder())
    assert created == []
    retriever.search("brute force", 1, 5.0)
    retriever.search("valid accounts", 1, 5.0)
    assert len(created) == 1


def test_localhost_is_mapped_to_ipv4() -> None:
    client = knowledge.qdrant_client("http://localhost:6333", 5, "test-api-key-0123456789-abcdefghijkl")
    assert "127.0.0.1:6333" in str(client._client.rest_uri)  # type: ignore[attr-defined]  # no public accessor


def test_warm_reports_whether_the_model_loads(memory: QdrantClient) -> None:
    assert QdrantRetriever(lambda: memory, COLLECTION, HashEmbedder()).warm() is True
    assert QdrantRetriever(lambda: memory, COLLECTION, HashEmbedder(fail=True)).warm() is False
