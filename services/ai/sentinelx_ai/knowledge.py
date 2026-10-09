"""Approved security knowledge: corpus, embeddings, Qdrant ingestion and retrieval (D-026, D-063, D-070-D-072).

Usage: python -m sentinelx_ai.knowledge   (owner role; syncs fixtures/ into knowledge_documents and Qdrant)

One document is one retrieval unit: the curated MITRE techniques (fixtures/mitre_techniques.json) plus the playbooks
(fixtures/knowledge/playbooks.json). Each document has a stable `kd_` row in `knowledge_documents` and one Qdrant point
whose payload carries that ID, so every hit is a source reference (D-018).
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import ValidationError
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams

from .config import REPO_ROOT, pg_connect_options
from .tools import KnowledgeHit

EMBEDDING_MODEL: Final = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_REVISION: Final = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"  # pinned Hub commit, Apache-2.0 (D-070)
EMBEDDING_DIMENSION: Final = 384
DEFAULT_COLLECTION: Final = "security_knowledge"
POINT_NAMESPACE: Final = uuid.UUID("5d1c1f6e-6f3b-4f4c-9d0e-3a3b8f2c9a10")  # stable point IDs per (source, external_id)
MITRE_SOURCE: Final = "mitre-attack"
MAX_TEXT_CHARS: Final = 1500  # KnowledgeHit.snippet bound
FIXTURES: Final = REPO_ROOT / "fixtures"


@dataclass(frozen=True)
class Document:
    source: str
    external_id: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Changes when the text or the embedding model changes, so stale vectors are detectable."""
        material = json.dumps([self.title, self.text, EMBEDDING_MODEL, EMBEDDING_REVISION]).encode()
        return hashlib.sha256(material).hexdigest()

    @property
    def point_id(self) -> str:
        return str(uuid.uuid5(POINT_NAMESPACE, f"{self.source}:{self.external_id}"))


def load_corpus() -> list[Document]:
    mitre = json.loads((FIXTURES / "mitre_techniques.json").read_text(encoding="utf-8"))
    playbooks = json.loads((FIXTURES / "knowledge" / "playbooks.json").read_text(encoding="utf-8"))
    documents = [
        Document(
            source=MITRE_SOURCE,
            external_id=t["technique_id"],
            title=f"{t['technique_id']} {t['name']}",
            text=(
                f"MITRE ATT&CK {t['technique_id']} {t['name']} (tactics: {', '.join(t['tactics'])}). {t['description']}"
            ),
            metadata={"attack_version": mitre["attack_version"], "tactics": t["tactics"]},
        )
        for t in mitre["techniques"]
    ]
    documents += [
        Document(
            source=playbooks["source"],
            external_id=d["external_id"],
            title=d["title"],
            text=d["text"],
            metadata={"techniques": d["techniques"]},
        )
        for d in playbooks["documents"]
    ]
    for d in documents:
        if not d.text or len(d.text) > MAX_TEXT_CHARS:
            raise ValueError(f"{d.source}/{d.external_id}: text must be 1-{MAX_TEXT_CHARS} characters")
    keys = [(d.source, d.external_id) for d in documents]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate (source, external_id) in the knowledge corpus")
    return documents


# ---------------------------------------------------------------------------------------------------------------------
# Embeddings.


class Embedder(Protocol):
    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceEmbedder:
    """all-MiniLM-L6-v2 on CPU, normalized (cosine). Loaded on first use; thread-safe for the background tasks."""

    def __init__(self) -> None:
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer  # heavy import (torch); only when needed

                self._model = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_REVISION, device="cpu")
            return self._model

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._load().encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [[float(x) for x in v] for v in vectors]


# ---------------------------------------------------------------------------------------------------------------------
# Retrieval.


def qdrant_client(url: str, timeout_seconds: int) -> QdrantClient:
    """IPv4 for `localhost`: on Windows `localhost` tries ::1 first and every call took 2 s more (as D-051)."""
    parts = urlsplit(url)
    if parts.hostname == "localhost":
        url = urlunsplit(parts._replace(netloc=parts.netloc.replace("localhost", "127.0.0.1", 1)))
    # Versions are pinned together (client 1.15.1, server 1.15.0, D-070); skip the network check at construction.
    return QdrantClient(url=url, timeout=timeout_seconds, check_compatibility=False)


class QdrantRetriever:
    """`KnowledgeRetriever` over Qdrant (D-063): TimeoutError/ConnectionError on failure, at most top_k hits.

    The client is created on the first search (constructing one costs about 0.5 s).
    """

    def __init__(self, connect: Callable[[], QdrantClient], collection: str, embedder: Embedder) -> None:
        self._connect, self._collection, self._embedder = connect, collection, embedder
        self._client: QdrantClient | None = None

    def warm(self) -> bool:
        """Loads the embedding model ahead of the first search (a cold load took 19 s); False if it cannot load."""
        try:
            self._embedder.encode(["warm-up"])
        except Exception:  # noqa: BLE001 - reported by the caller; searches then fail as unavailable
            return False
        return True

    def search(self, query: str, top_k: int, timeout_seconds: float) -> list[KnowledgeHit]:
        try:
            vector = self._embedder.encode([query])[0]
        except Exception as error:  # noqa: BLE001 - model missing or not downloadable: retrieval is unavailable
            raise ConnectionError(f"embedding model unavailable ({type(error).__name__})") from error
        self._client = self._client or self._connect()
        try:
            points = self._client.query_points(
                self._collection, query=vector, limit=top_k, with_payload=True, timeout=max(1, int(timeout_seconds))
            ).points
        except ResponseHandlingException as error:
            if isinstance(error.source, httpx.TimeoutException):
                raise TimeoutError("Qdrant did not answer in time") from error
            raise ConnectionError("Qdrant is unreachable") from error
        except UnexpectedResponse as error:  # e.g. the collection was never ingested
            raise ConnectionError(f"Qdrant returned HTTP {error.status_code}") from error
        hits = []
        for point in points:
            payload = point.payload or {}
            try:
                hits.append(
                    KnowledgeHit(
                        document_id=payload.get("document_id", ""),
                        source=payload.get("source", ""),
                        external_id=payload.get("external_id", ""),
                        title=payload.get("title", ""),
                        snippet=payload.get("text", ""),
                        score=point.score,
                    )
                )
            except ValidationError:
                continue  # a point that does not carry a valid source reference is never returned
        return hits[:top_k]


# ---------------------------------------------------------------------------------------------------------------------
# Ingestion (owner role, like `npm run db:seed`).

UPSERT_DOCUMENT_SQL: Final = """
INSERT INTO knowledge_documents (source, external_id, title, content_hash, qdrant_point_id, metadata_json)
VALUES (%(source)s, %(external_id)s, %(title)s, %(content_hash)s, %(point_id)s, %(metadata)s)
ON CONFLICT (source, external_id) DO UPDATE
SET title = EXCLUDED.title, content_hash = EXCLUDED.content_hash, qdrant_point_id = EXCLUDED.qdrant_point_id,
    metadata_json = EXCLUDED.metadata_json
RETURNING id
"""


@dataclass(frozen=True)
class IngestCounts:
    documents: int
    removed: int


def ensure_collection(client: QdrantClient, collection: str) -> None:
    """Creates the cosine collection; recreates it when the vector size no longer matches the model."""
    if client.collection_exists(collection):
        vectors = client.get_collection(collection).config.params.vectors
        if isinstance(vectors, VectorParams) and vectors.size == EMBEDDING_DIMENSION:
            return
        client.delete_collection(collection)
    client.create_collection(
        collection, vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE)
    )


def ingest(owner_url: str, client: QdrantClient, collection: str, embedder: Embedder) -> IngestCounts:
    """Syncs the corpus: upserts rows and points, removes rows and points no longer in the corpus. Idempotent."""
    import psycopg  # owner-only path; keeps the import out of retrieval
    from psycopg.types.json import Jsonb

    documents = load_corpus()
    vectors = embedder.encode([f"{d.title}. {d.text}" for d in documents])
    ensure_collection(client, collection)
    with psycopg.connect(owner_url, **pg_connect_options(owner_url)) as conn:
        ids = [
            conn.execute(
                UPSERT_DOCUMENT_SQL,
                {
                    "source": d.source,
                    "external_id": d.external_id,
                    "title": d.title,
                    "content_hash": d.content_hash,
                    "point_id": d.point_id,
                    "metadata": Jsonb(d.metadata),
                },
            ).fetchone()
            for d in documents
        ]
        stale = conn.execute(
            "DELETE FROM knowledge_documents WHERE NOT (id = ANY(%(keep)s)) RETURNING qdrant_point_id",
            {"keep": [row[0] for row in ids if row]},
        ).fetchall()
    client.upsert(
        collection,
        points=[
            PointStruct(
                id=d.point_id,
                vector=v,
                payload={
                    "document_id": row[0],
                    "source": d.source,
                    "external_id": d.external_id,
                    "title": d.title,
                    "text": d.text,
                    "content_hash": d.content_hash,
                },
            )
            for d, v, row in zip(documents, vectors, ids, strict=True)
            if row
        ],
        wait=True,
    )
    stale_points = [p for (p,) in stale if p]
    if stale_points:
        client.delete(collection, points_selector=PointIdsList(points=stale_points), wait=True)
    return IngestCounts(documents=len(documents), removed=len(stale))


def main() -> int:
    import os

    from .config import load_root_env
    from .log import log

    load_root_env()
    owner_url = os.environ.get("DATABASE_URL", "")
    if not owner_url:
        log("error", "knowledge.config_invalid", message="DATABASE_URL is not set")
        return 1
    collection = os.environ.get("KNOWLEDGE_COLLECTION") or DEFAULT_COLLECTION
    client = qdrant_client(os.environ.get("QDRANT_URL") or "http://localhost:6333", 30)
    counts = ingest(owner_url, client, collection, SentenceEmbedder())
    log("info", "knowledge.ingest", collection=collection, documents=counts.documents, removed=counts.removed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
