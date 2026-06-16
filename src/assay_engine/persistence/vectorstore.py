"""Local vector store seam (ADR-0003) — loopback-enforced Qdrant factory.

Ported and generalized from the prior platform. The client is constructed only against a
loopback host; the guard fires *before* importing the (optional ``persistence`` extra)
``qdrant_client``, so a misconfigured remote host is rejected regardless of whether the
package is installed.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Protocol, Sequence, runtime_checkable

from assay_engine._local import require_loopback_host

VECTOR_HOST = os.environ.get("ASSAY_VECTOR_HOST", "localhost")
VECTOR_HTTP_PORT = int(os.environ.get("ASSAY_VECTOR_HTTP_PORT", "6333"))

# Stable namespace for mapping the engine's string ids onto Qdrant point UUIDs.
_POINT_NS = uuid.UUID("a55a9e00-0000-4000-8000-000000000001")


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None: ...
    def query(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]: ...


def vector_store_url() -> str:
    host = require_loopback_host(VECTOR_HOST, what="vector store host")
    return f"http://{host}:{VECTOR_HTTP_PORT}"


def get_qdrant_client() -> Any:
    """Construct a loopback-only Qdrant client (lazy import of the optional extra)."""
    host = require_loopback_host(VECTOR_HOST, what="vector store host")  # before any import
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "vector store requires the 'persistence' extra (qdrant-client) — not installed"
        ) from exc
    return QdrantClient(host=host, port=VECTOR_HTTP_PORT)


def _point_id(ref: str) -> str:
    """Deterministic Qdrant point UUID for an engine string id (Qdrant ids must be int/UUID)."""
    return str(uuid.uuid5(_POINT_NS, ref))


class QdrantVectorStore:
    """Reference :class:`VectorStore` over a loopback Qdrant collection (cosine).

    The engine's ids are arbitrary strings; Qdrant point ids must be int/UUID, so each id is
    mapped to a deterministic UUID and the original id is stored in the point payload (and
    returned by ``query``). This is a goal-agnostic reference implementation; a study may
    supply its own ``VectorStore`` (collection naming, distance, sharding are study choices).
    """

    def __init__(self, collection: str, dim: int, *, client: Any | None = None) -> None:
        self._collection = collection
        self._dim = dim
        self._client = client if client is not None else get_qdrant_client()

    def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )

    def upsert(
        self, ids: Sequence[str], vectors: Sequence[Sequence[float]], *, batch_size: int = 256
    ) -> None:
        from qdrant_client.models import PointStruct

        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must have equal length")
        points = [
            PointStruct(id=_point_id(i), vector=list(v), payload={"ref": i})
            for i, v in zip(ids, vectors)
        ]
        # Chunk so a large ingest cannot exceed the server's request payload limit (Qdrant
        # guidance: do not upload points one-by-one, but bound the batch size).
        for start in range(0, len(points), batch_size):
            self._client.upsert(self._collection, points=points[start : start + batch_size])

    def query(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]:
        res = self._client.query_points(
            self._collection, query=list(vector), limit=k, with_payload=True
        )
        return [(p.payload["ref"], float(p.score)) for p in res.points]
