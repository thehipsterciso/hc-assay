"""Data versioning seam (contract + stub).

Content-addressed versioning of inputs and artifacts so every finding cites the exact bytes
it was computed from (METHODOLOGY.md §7). Backed by a local data-versioning tool when wired.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DataVersioner(Protocol):
    def put(self, path: str) -> str:
        """Version the artifact at ``path``; return its content hash / version id."""
        ...

    def fingerprint(self, path: str) -> str:
        """Return the content hash of ``path`` without storing it."""
        ...
