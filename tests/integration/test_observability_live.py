"""Live observability — real MLflow lifecycle + real OpenTelemetry tracing wiring."""

from __future__ import annotations

import pytest

from tests.integration.conftest import have


@pytest.mark.skipif(not have("mlflow"), reason="observability extra (mlflow) not installed")
def test_mlflow_full_lifecycle_real_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSAY_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    from assay_engine.observability.tracking import MlflowExperimentTracker

    tracker = MlflowExperimentTracker(experiment="integration")
    run_id = tracker.start_run("r1", {"alpha": "0.05", "builder": "demo"})
    tracker.log_metric(run_id, "score", 0.9)
    artifact = tmp_path / "note.txt"
    artifact.write_text("hello")
    tracker.log_artifact(run_id, str(artifact))
    tracker.end_run(run_id)

    from mlflow.tracking import MlflowClient

    run = MlflowClient(tracking_uri=tracker._uri).get_run(run_id)
    assert run.data.metrics["score"] == 0.9
    assert run.data.params["alpha"] == "0.05"
    assert run.info.status == "FINISHED"


@pytest.mark.skipif(not have("opentelemetry"), reason="opentelemetry not installed")
def test_run_trace_context_real_otel_attaches_and_detaches():
    from opentelemetry import baggage, context

    from assay_engine.observability.tracing import run_trace_context

    with run_trace_context("run-xyz"):
        assert baggage.get_baggage("assay.run_id") == "run-xyz"
    # detached after the block — no leaked baggage in the current context
    assert baggage.get_baggage("assay.run_id", context.get_current()) is None


@pytest.mark.skipif(not have("opentelemetry"), reason="opentelemetry not installed")
def test_otel_tracer_span_emits_without_error():
    from assay_engine.observability.tracing import OtelTracer

    # Real span creation via the global provider — must not raise even with no live collector.
    with OtelTracer().span("integration.span", {"k": "v"}):
        pass


@pytest.mark.skipif(not have("phoenix"), reason="observability extra (phoenix) not installed")
def test_bootstrap_tracing_real_provider_and_idempotent(monkeypatch):
    import assay_engine.observability.tracing as tr

    monkeypatch.delenv("ASSAY_DISABLE_TRACING", raising=False)
    monkeypatch.setattr(tr, "_provider", None)
    p1 = tr.bootstrap_tracing()
    assert p1 is not None  # real Phoenix TracerProvider registered (batch, async export)
    assert tr.bootstrap_tracing() is p1  # idempotent — same cached provider, no re-register
