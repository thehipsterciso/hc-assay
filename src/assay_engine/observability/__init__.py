"""Observability — self-hosted tracing + experiment tracking (ADR-0003).

On-box only: OpenTelemetry spans to a local collector, and a local experiment-tracking
store for runs, parameters, and artifacts. No SaaS observability — analyzed content never
leaves the machine. Lifted from the prior platform's hardened tracing/tracking wiring.
"""

from assay_engine.observability.tracing import Tracer
from assay_engine.observability.tracking import ExperimentTracker

__all__ = ["Tracer", "ExperimentTracker"]
