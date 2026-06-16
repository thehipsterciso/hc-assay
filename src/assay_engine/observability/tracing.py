"""Self-hosted tracing — OpenTelemetry → a local collector (ADR-0003).

Ported and generalized from the prior platform's Phoenix/OTel bootstrap. Everything is
on-box: spans export over OTLP to a loopback-bound collector; nothing leaves the machine.
OpenTelemetry and the Phoenix collector are optional (the ``observability`` extra) and
imported lazily, so this module loads — and the engine runs untraced — with neither present.

The reasoning seam already emits spans through the global OTel tracer provider; calling
:func:`bootstrap_tracing` once at startup wires that global provider at a local collector so
those spans land somewhere. Without the extra (or with ``ASSAY_DISABLE_TRACING`` set),
tracing degrades to a silent no-op.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

from assay_engine._local import require_loopback_host

# Local collector endpoint (loopback-enforced).
TRACING_HOST = os.environ.get("ASSAY_TRACING_HOST", "localhost")
TRACING_PORT = int(os.environ.get("ASSAY_TRACING_PORT", "6006"))
PROJECT_NAME = os.environ.get("ASSAY_TRACING_PROJECT", "assay")

_provider: Any = None


def _disabled() -> bool:
    return os.environ.get("ASSAY_DISABLE_TRACING", "").strip().lower() in {"1", "true", "yes", "on"}


def tracing_base_url() -> str:
    require_loopback_host(TRACING_HOST, what="tracing collector host")
    return f"http://{TRACING_HOST}:{TRACING_PORT}"


def tracing_endpoint() -> str:
    """OTLP/HTTP traces endpoint at the local collector (loopback-enforced)."""
    return f"{tracing_base_url()}/v1/traces"


def bootstrap_tracing() -> Any:
    """Idempotently wire the global OTel tracer provider to the local collector.

    Returns the provider, or ``None`` if tracing is disabled, the extra is not installed, or
    setup fails — tracing must never be load-bearing, so this degrades gracefully.
    """
    global _provider
    if _disabled():
        return None
    if _provider is not None:
        return _provider
    try:
        require_loopback_host(TRACING_HOST, what="tracing collector host")
        from phoenix.otel import register

        _provider = register(
            project_name=PROJECT_NAME,
            endpoint=tracing_endpoint(),
            set_global_tracer_provider=True,
        )
        return _provider
    except Exception:
        # Missing extra / collector down / registration race — run untraced.
        return None


@contextmanager
def run_trace_context(run_id: str | None) -> Iterator[None]:
    """Stamp ``run_id`` onto every span emitted inside the block (cross-store correlation).

    A no-op when ``run_id`` is None or OpenTelemetry is absent.
    """
    if run_id is None:
        yield
        return
    try:
        from opentelemetry import baggage, context
    except ImportError:
        yield
        return
    token = context.attach(baggage.set_baggage("assay.run_id", run_id))
    try:
        yield
    finally:
        context.detach(token)


@runtime_checkable
class Tracer(Protocol):
    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        ...


class OtelTracer:
    """A tracer that emits OpenTelemetry spans via the global provider (no-op if OTel absent).

    Use this where a component wants explicit spans rather than relying on auto-instrumentation;
    it honors whatever provider :func:`bootstrap_tracing` registered.
    """

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        try:
            from opentelemetry import trace
        except ImportError:
            yield
            return
        tracer = trace.get_tracer("assay_engine")
        with tracer.start_as_current_span(name) as sp:
            for k, v in (attributes or {}).items():
                sp.set_attribute(k, v)
            yield


class UnconfiguredTracer:
    """Fail-loud placeholder for contexts that must not silently drop spans."""

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        raise NotImplementedError(
            "no tracer configured — call bootstrap_tracing() and use OtelTracer, or supply a "
            "test double"
        )
        yield  # pragma: no cover - keeps this a generator/contextmanager
