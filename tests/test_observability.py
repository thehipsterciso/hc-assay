"""Observability port — tracing + experiment tracking, all offline (no extra installed)."""

import pytest

from assay_engine._local import NonLocalEndpointError
from assay_engine.observability import tracing as tr
from assay_engine.observability.tracing import (
    OtelTracer,
    UnconfiguredTracer,
    bootstrap_tracing,
    run_trace_context,
    tracing_endpoint,
)
from assay_engine.observability.tracking import (
    MlflowExperimentTracker,
    get_tracking_uri,
)


# ---- tracing ----

def test_bootstrap_returns_none_when_disabled(monkeypatch):
    monkeypatch.setenv("ASSAY_DISABLE_TRACING", "1")
    assert bootstrap_tracing() is None


def test_bootstrap_returns_none_when_extra_absent(monkeypatch):
    # phoenix is not installed in this env -> graceful degradation, never raises
    monkeypatch.delenv("ASSAY_DISABLE_TRACING", raising=False)
    monkeypatch.setattr(tr, "_provider", None)
    assert bootstrap_tracing() is None


def test_tracing_endpoint_is_loopback():
    assert tracing_endpoint().startswith("http://localhost:")


def test_tracing_endpoint_rejects_non_loopback(monkeypatch):
    monkeypatch.setattr(tr, "TRACING_HOST", "10.0.0.5")
    with pytest.raises(NonLocalEndpointError):
        tracing_endpoint()


def test_run_trace_context_noop_without_run_id():
    with run_trace_context(None):
        pass  # must not raise


def test_run_trace_context_noop_without_otel():
    # opentelemetry absent -> the context manager is a safe no-op even with a run_id
    with run_trace_context("run-1"):
        pass


def test_otel_tracer_span_is_noop_without_otel():
    with OtelTracer().span("x", {"a": 1}):
        pass  # must not raise when opentelemetry is absent


def test_unconfigured_tracer_fails_loud():
    with pytest.raises(NotImplementedError):
        with UnconfiguredTracer().span("x"):
            pass


# ---- experiment tracking ----

def test_bootstrap_is_idempotent(monkeypatch):
    monkeypatch.delenv("ASSAY_DISABLE_TRACING", raising=False)
    sentinel = object()
    monkeypatch.setattr(tr, "_provider", sentinel)
    assert bootstrap_tracing() is sentinel  # cached provider returned, not re-registered


def test_get_tracking_uri_resolves_sqlite_to_absolute_path(monkeypatch):
    import os

    monkeypatch.delenv("ASSAY_TRACKING_URI", raising=False)
    uri = get_tracking_uri()
    assert uri.startswith("sqlite:///")
    path = uri[len("sqlite:///") :]
    assert os.path.isabs(path)  # genuinely absolute, not a circular prefix check


@pytest.mark.parametrize(
    "uri",
    ["sqlite://evil.com/x.db", "//evil.com/share", "http://0.0.0.0:5000", "postgresql://db.example.com/m"],
)
def test_get_tracking_uri_rejects_non_local(monkeypatch, uri):
    monkeypatch.setenv("ASSAY_TRACKING_URI", uri)
    with pytest.raises(NonLocalEndpointError):
        get_tracking_uri()


def test_get_tracking_uri_rejects_remote(monkeypatch):
    monkeypatch.setenv("ASSAY_TRACKING_URI", "http://mlflow.example.com:5000")
    with pytest.raises(NonLocalEndpointError):
        get_tracking_uri()


def test_tracker_construction_validates_uri_without_mlflow(monkeypatch):
    # constructs (validates local URI) even though mlflow is not installed
    monkeypatch.delenv("ASSAY_TRACKING_URI", raising=False)
    tracker = MlflowExperimentTracker(experiment="t")
    assert tracker._uri.startswith("sqlite:///")


def test_tracker_construction_rejects_remote(monkeypatch):
    monkeypatch.setenv("ASSAY_TRACKING_URI", "postgresql://db.example.com/mlflow")
    with pytest.raises(NonLocalEndpointError):
        MlflowExperimentTracker()


def test_tracker_start_run_fails_loud_without_mlflow(monkeypatch):
    monkeypatch.delenv("ASSAY_TRACKING_URI", raising=False)
    tracker = MlflowExperimentTracker()
    with pytest.raises(RuntimeError, match="observability' extra"):
        tracker.start_run("r", {})


def test_tracker_full_lifecycle_against_local_store(monkeypatch, tmp_path):
    # issue #O1: start_run -> log_metric -> log_artifact -> end_run must not collide on the
    # active-run stack. Runs only when the observability extra (mlflow) is installed.
    pytest.importorskip("mlflow")
    db = tmp_path / "mlflow.db"
    monkeypatch.setenv("ASSAY_TRACKING_URI", f"sqlite:///{db}")
    tracker = MlflowExperimentTracker(experiment="lifecycle-test")
    run_id = tracker.start_run("r1", {"alpha": "0.05"})
    tracker.log_metric(run_id, "score", 0.9)  # would raise on the old active-stack design
    artifact = tmp_path / "note.txt"
    artifact.write_text("hi")
    tracker.log_artifact(run_id, str(artifact))
    tracker.end_run(run_id)
    from mlflow.tracking import MlflowClient

    run = MlflowClient(tracking_uri=f"sqlite:///{db}").get_run(run_id)
    assert run.data.metrics["score"] == 0.9
    assert run.info.status == "FINISHED"
