"""Experiment tracking — a local, on-box run/metric/artifact store (ADR-0003).

Ported and generalized from the prior platform's MLflow setup. The backend is a local store
(default: a SQLite file under the working directory); a remote tracking server is rejected by
the local-URI guard. MLflow is optional (the ``observability`` extra) and imported lazily, so
this module loads without it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from assay_engine._local import require_local_uri

_DEFAULT_URI = "sqlite:///assay_mlflow.db"
EXPERIMENT_NAME = os.environ.get("ASSAY_EXPERIMENT", "assay")


def get_tracking_uri() -> str:
    """Resolve the tracking URI (env override, else local SQLite), enforced local."""
    uri = os.environ.get("ASSAY_TRACKING_URI", _DEFAULT_URI)
    # Resolve a relative sqlite path to an absolute file so runs land deterministically.
    prefix = "sqlite:///"
    if uri.startswith(prefix):
        rel = uri[len(prefix) :]
        if not os.path.isabs(rel):
            uri = prefix + str((Path.cwd() / rel).resolve())
    return require_local_uri(uri, what="experiment tracking")


# Structural Protocol only — adapter/seam validation is behavior-based, not isinstance (#148).
class ExperimentTracker(Protocol):
    def start_run(self, name: str, params: Mapping[str, Any]) -> str: ...
    def log_metric(self, run_id: str, key: str, value: float) -> None: ...
    def log_artifact(self, run_id: str, path: str) -> None: ...
    def end_run(self, run_id: str, status: str = "FINISHED") -> None: ...


class MlflowExperimentTracker:
    """A local-store experiment tracker backed by MLflow (lazy import).

    Construction validates the tracking URI is local and selects the experiment; it does not
    import MLflow until a run is started, so the module is importable without the extra.
    """

    def __init__(self, experiment: str = EXPERIMENT_NAME) -> None:
        self._experiment = experiment
        self._uri = get_tracking_uri()  # validates local before anything else

    def _client(self) -> Any:
        """An MlflowClient bound to the local store. Uses the client API (keyed by run_id)
        throughout, so no run ever sits on the global active-run stack — start_run followed by
        log_metric cannot collide (audit issue #O1)."""
        try:
            from mlflow.tracking import MlflowClient
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RuntimeError(
                "experiment tracking requires the 'observability' extra (mlflow) — not installed"
            ) from exc
        return MlflowClient(tracking_uri=self._uri)

    def _experiment_id(self, client: Any) -> str:
        exp = client.get_experiment_by_name(self._experiment)
        if exp is not None:
            return str(exp.experiment_id)
        return str(client.create_experiment(self._experiment))

    def start_run(self, name: str, params: Mapping[str, Any]) -> str:
        client = self._client()
        run = client.create_run(self._experiment_id(client), run_name=name)
        run_id = str(run.info.run_id)
        # The run now exists in the store. If param-logging fails partway (network blip, server
        # error), the run would otherwise be orphaned permanently in RUNNING state — phantom runs
        # accumulate over time (pass 3, #F-023). Terminate it FAILED on any param-logging error
        # before re-raising, so a created run is never left dangling.
        try:
            for k, v in dict(params).items():
                client.log_param(run_id, k, v)
        except Exception:
            try:
                client.set_terminated(run_id, status="FAILED")
            except Exception:  # noqa: BLE001,S110 - best-effort cleanup; original error re-raised
                pass
            raise
        return run_id

    def log_metric(self, run_id: str, key: str, value: float) -> None:
        self._client().log_metric(run_id, key, value)

    def log_artifact(self, run_id: str, path: str) -> None:
        self._client().log_artifact(run_id, path)

    def end_run(self, run_id: str, status: str = "FINISHED") -> None:
        # MLflow run statuses: FINISHED / FAILED / KILLED. Recording FAILED makes a failed run
        # distinguishable from a successful one in the store (#110).
        self._client().set_terminated(run_id, status=status)
