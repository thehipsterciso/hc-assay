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

def test_get_tracking_uri_resolves_sqlite_absolute(monkeypatch):
    monkeypatch.delenv("ASSAY_TRACKING_URI", raising=False)
    uri = get_tracking_uri()
    assert uri.startswith("sqlite:////") or uri.startswith("sqlite:///" + "/")  # absolute path


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
