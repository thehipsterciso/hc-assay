"""Observability — self-hosted tracing + experiment tracking (ADR-0003).

On-box only: OpenTelemetry spans to a local collector, and a local experiment-tracking store.
No SaaS observability — analyzed content never leaves the machine. Ported and generalized
from the prior platform's Phoenix/OTel + MLflow wiring; backends are optional (the
``observability`` extra) and imported lazily.
"""

from assay_engine.observability.tracking import (
    EXPERIMENT_NAME,
    ExperimentTracker,
    MlflowExperimentTracker,
    get_tracking_uri,
)
from assay_engine.observability.tracing import (
    OtelTracer,
    Tracer,
    UnconfiguredTracer,
    bootstrap_tracing,
    run_trace_context,
    tracing_base_url,
    tracing_endpoint,
)

__all__ = [
    "Tracer",
    "OtelTracer",
    "UnconfiguredTracer",
    "bootstrap_tracing",
    "run_trace_context",
    "tracing_base_url",
    "tracing_endpoint",
    "ExperimentTracker",
    "MlflowExperimentTracker",
    "EXPERIMENT_NAME",
    "get_tracking_uri",
]
