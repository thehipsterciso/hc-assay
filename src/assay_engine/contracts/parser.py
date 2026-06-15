"""Ingestion parser interface — the only adapter piece that understands the raw format.

An adapter implements :class:`IngestionParser` to turn its native source into a canonical
:class:`~assay_engine.contracts.schema.Corpus`. The engine calls ``parse`` and works only
with the canonical result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from assay_engine.contracts.schema import Corpus


@runtime_checkable
class IngestionParser(Protocol):
    """Raw source → canonical :class:`Corpus`.

    Implementations live in adapters. They must be deterministic: the same source bytes
    produce the same ``Corpus`` (so the baseline is reproducible). Implementations must not
    read any external-claims artifact here — claims load through a separate provider.
    """

    def parse(self, source: Path) -> Corpus:
        """Parse ``source`` into a canonical corpus."""
        ...

    def source_fingerprint(self, source: Path) -> str:
        """Return a stable content hash of ``source`` for provenance and determinism checks."""
        ...
