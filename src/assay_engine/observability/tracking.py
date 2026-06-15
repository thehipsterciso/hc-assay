"""Experiment tracking seam (contract + stub).

A local experiment-tracking store records each run's parameters, metrics, and artifact
references for the reproducibility package (METHODOLOGY.md §7). On-box only. Lifted from the
prior platform's tracking integration.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ExperimentTracker(Protocol):
    def start_run(self, name: str, params: Mapping[str, Any]) -> str:
        """Begin a tracked run; return its run id."""
        ...

    def log_metric(self, run_id: str, key: str, value: float) -> None:
        ...

    def log_artifact(self, run_id: str, path: str) -> None:
        ...

    def end_run(self, run_id: str) -> None:
        ...
