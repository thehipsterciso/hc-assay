"""Experiment tracking — a local, on-box run/metric/artifact store (ADR-0003).

Ported and generalized from the prior platform's MLflow setup. The backend is a local store
(default: a SQLite file under the working directory); a remote tracking server is rejected by
the local-URI guard. MLflow is optional (the ``observability`` extra) and imported lazily, so
this module loads without it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

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


@runtime_checkable
class ExperimentTracker(Protocol):
    def start_run(self, name: str, params: Mapping[str, Any]) -> str: ...
    def log_metric(self, run_id: str, key: str, value: float) -> None: ...
    def log_artifact(self, run_id: str, path: str) -> None: ...
    def end_run(self, run_id: str) -> None: ...


class MlflowExperimentTracker:
    """A local-store experiment tracker backed by MLflow (lazy import).

    Construction validates the tracking URI is local and selects the experiment; it does not
    import MLflow until a run is started, so the module is importable without the extra.
    """

    def __init__(self, experiment: str = EXPERIMENT_NAME) -> None:
        self._experiment = experiment
        self._uri = get_tracking_uri()  # validates local before anything else

    def _mlflow(self) -> Any:
        try:
            import mlflow
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RuntimeError(
                "experiment tracking requires the 'observability' extra (mlflow) — not installed"
            ) from exc
        mlflow.set_tracking_uri(self._uri)
        mlflow.set_experiment(self._experiment)
        return mlflow

    def start_run(self, name: str, params: Mapping[str, Any]) -> str:
        mlflow = self._mlflow()
        run = mlflow.start_run(run_name=name)
        if params:
            mlflow.log_params(dict(params))
        return str(run.info.run_id)

    def log_metric(self, run_id: str, key: str, value: float) -> None:
        mlflow = self._mlflow()
        with mlflow.start_run(run_id=run_id):
            mlflow.log_metric(key, value)

    def log_artifact(self, run_id: str, path: str) -> None:
        mlflow = self._mlflow()
        with mlflow.start_run(run_id=run_id):
            mlflow.log_artifact(path)

    def end_run(self, run_id: str) -> None:
        mlflow = self._mlflow()
        mlflow.end_run()
