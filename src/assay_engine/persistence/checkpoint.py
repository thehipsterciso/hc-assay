"""Durable checkpointer seam (contract + stub).

Persists run state at phase boundaries so a study resumes deterministically. Backed by a
local database when wired (lifted from the prior platform's durable checkpointer).
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class Checkpointer(Protocol):
    def save(self, run_id: str, phase: str, state: Mapping[str, Any]) -> None:
        ...

    def load(self, run_id: str) -> Mapping[str, Any] | None:
        ...
