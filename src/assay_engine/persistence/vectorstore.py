"""Local vector store seam (contract + stub).

Stores and queries embeddings produced by the baseline toolkit. Local only. Backed by an
on-box vector database when wired (lifted from the prior platform).
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        ...

    def query(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]:
        """Return the ``k`` nearest ids with their distances."""
        ...
