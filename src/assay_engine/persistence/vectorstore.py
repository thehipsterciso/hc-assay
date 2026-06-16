"""Local vector store seam (ADR-0003) — loopback-enforced Qdrant factory.

Ported and generalized from the prior platform. The client is constructed only against a
loopback host; the guard fires *before* importing the (optional ``persistence`` extra)
``qdrant_client``, so a misconfigured remote host is rejected regardless of whether the
package is installed.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, Sequence, runtime_checkable

from assay_engine._local import require_loopback_host

VECTOR_HOST = os.environ.get("ASSAY_VECTOR_HOST", "localhost")
VECTOR_HTTP_PORT = int(os.environ.get("ASSAY_VECTOR_HTTP_PORT", "6333"))


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
