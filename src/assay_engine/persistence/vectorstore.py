"""Local vector store seam (ADR-0003) — loopback-enforced Qdrant factory.

Ported and generalized from the prior platform. The client is constructed only against a
loopback host; the guard fires *before* importing the (optional ``persistence`` extra)
``qdrant_client``, so a misconfigured remote host is rejected regardless of whether the
package is installed.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Protocol, Sequence

from assay_engine._local import require_loopback_host

VECTOR_HOST = os.environ.get("ASSAY_VECTOR_HOST", "localhost")


def _int_env(name: str, default: str) -> int:
    """Parse an int env var with a clear error naming the var (#H-022).

    A bare ``int(os.environ[...])`` at import time raises an opaque ``ValueError: invalid literal
    for int()`` that doesn't say WHICH var was misconfigured, and it fires during import.
    """
    raw = os.environ.get(name, default)
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be an integer; got {raw!r}") from exc


VECTOR_HTTP_PORT = _int_env("ASSAY_VECTOR_HTTP_PORT", "6333")

# Stable namespace for mapping the engine's string ids onto Qdrant point UUIDs.
_POINT_NS = uuid.UUID("a55a9e00-0000-4000-8000-000000000001")


# Structural Protocol only — adapter/seam validation is behavior-based, not isinstance (#148).
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
        # Track ownership: only close a client we created ourselves; an injected client is the
        # caller's to manage (#117).
        self._owns_client = client is None
        self._client = client if client is not None else get_qdrant_client()

    def close(self) -> None:
        """Close the underlying client if this store created it (no-op for an injected one)."""
        if self._owns_client:
            close = getattr(self._client, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> "QdrantVectorStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

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
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        # Build each batch of PointStructs lazily, so only one batch is materialized in memory at
        # a time (bounding BOTH payload AND memory) rather than boxing the whole corpus up front
        # (#118). Qdrant guidance: don't upload point-by-point, but bound the batch.
        for start in range(0, len(ids), batch_size):
            batch = [
                PointStruct(id=_point_id(ids[j]), vector=list(vectors[j]), payload={"ref": ids[j]})
                for j in range(start, min(start + batch_size, len(ids)))
            ]
            self._client.upsert(self._collection, points=batch)

    def query(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]:
        if k <= 0:
            raise ValueError(f"k must be a positive integer; got {k}")  # #H-021
        res = self._client.query_points(
            self._collection, query=list(vector), limit=k, with_payload=True
        )
        # A returned point without our 'ref' payload (e.g. inserted by another writer) would raise
        # an opaque KeyError/TypeError; skip such points defensively rather than crash the query
        # (#H-021). The store only ever upserts points carrying 'ref', so this is belt-and-braces.
        out: list[tuple[str, float]] = []
        for p in res.points:
            ref = (p.payload or {}).get("ref")
            if ref is not None:
                out.append((ref, float(p.score)))
        return out
