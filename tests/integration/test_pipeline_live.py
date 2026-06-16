"""Live end-to-end composition — the whole study pipeline against a REAL backend.

Unlike tests/test_pipeline.py (which runs the composition purely), this drives run_study with a
real OpenTelemetry tracer and asserts a span is actually emitted around every phase handoff —
proving the observability seam composes with the runner end-to-end, not just in isolation. The
full methodology (blind baseline → discovery/confirm → adjudicate/score) runs through it with an
intact, verifiable provenance trail.
"""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from assay_engine.contracts.study import StudyMode  # noqa: E402
from assay_engine.observability.tracing import OtelTracer  # noqa: E402
from assay_engine.orchestration.gates import GateDecision  # noqa: E402
from assay_engine.pipeline import run_study  # noqa: E402
from assay_engine.provenance import verify_records  # noqa: E402
from tests import reference_study as ref  # noqa: E402

ALL = frozenset(StudyMode)


def _exporter() -> InMemorySpanExporter:
    """Attach an in-memory span exporter to the active provider (or install an SDK one)."""
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        sdk = TracerProvider()
        sdk.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(sdk)
    return exporter


def test_full_pipeline_emits_real_spans_per_phase(tmp_path):
    exporter = _exporter()
    src = ref.write_source(tmp_path / "corpus.json")

    from assay_engine.pipeline import auto_approve
    result = run_study(ref.make_plan(src, modes=ALL), tracer=OtelTracer(), gate_handler=auto_approve)

    # the composed workflow produced real artifacts
    assert result.discovery_verdicts and result.scorecard is not None
    assert result.scorecard.total == 2
    verify_records(result.provenance)  # provenance chain intact across the live run

    trace.get_tracer_provider().force_flush()
    names = {s.name for s in exporter.get_finished_spans()}
    # a real span fired around every phase handoff
    for phase in ("INGEST", "BASELINE", "DISCOVERY", "PREREGISTER", "CONFIRM",
                  "ADJUDICATE", "SCORE", "REPORT"):
        assert f"phase:{phase}" in names, f"missing live span for {phase}: {sorted(names)}"


def test_full_pipeline_governance_gate_blocks_live(tmp_path):
    # the human gate genuinely halts the live run when the operator rejects
    _exporter()
    src = ref.write_source(tmp_path / "corpus.json")
    from assay_engine.orchestration.gates import GateError

    def reject(review) -> GateDecision:
        return GateDecision(approved=False, gate=review.gate, reason="operator rejected (live)")

    with pytest.raises(GateError):
        run_study(ref.make_plan(src, modes=ALL), tracer=OtelTracer(), gate_handler=reject)
