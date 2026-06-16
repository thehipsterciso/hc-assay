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

import atexit
import logging
import os
import signal
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

from assay_engine._local import require_loopback_host

_log = logging.getLogger("assay_engine.observability")

# Local collector endpoint (loopback-enforced).
TRACING_HOST = os.environ.get("ASSAY_TRACING_HOST", "localhost")
TRACING_PORT = int(os.environ.get("ASSAY_TRACING_PORT", "6006"))
PROJECT_NAME = os.environ.get("ASSAY_TRACING_PROJECT", "assay")

_provider: Any = None
# Guards the _provider check-then-set so concurrent bootstrap_tracing() calls don't race.
_provider_lock = threading.Lock()


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
    # Lock the check-then-set so two threads can't both register the global provider.
    with _provider_lock:
        if _provider is not None:
            return _provider
        try:
            require_loopback_host(TRACING_HOST, what="tracing collector host")
            # Bound the OTLP export so a downed collector can never hang teardown (#O3).
            os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "2")
            from phoenix.otel import register

            provider = register(
                project_name=PROJECT_NAME,
                endpoint=tracing_endpoint(),
                set_global_tracer_provider=True,
                batch=True,  # async BatchSpanProcessor — never block the run on export (#O2)
            )
            _provider = provider
            _warn_if_not_global(provider)
            _instrument_langchain()
            _install_flush_on_exit(provider)
            return _provider
        except Exception:
            # Missing extra / collector down / registration race — run untraced.
            return None


def _warn_if_not_global(provider: Any) -> None:
    """If another provider already won the global slot, our manual spans would vanish (#O6)."""
    try:
        from opentelemetry import trace

        if trace.get_tracer_provider() is not provider:
            _log.warning(
                "assay tracing: another OpenTelemetry provider holds the global slot; "
                "manually-emitted spans may not reach the local collector"
            )
    except Exception:
        pass


def _instrument_langchain() -> None:
    """Capture LangChain auto-spans (the bulk reasoning tier uses LangChain) — best-effort (#O5)."""
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(skip_dep_check=True)
    except Exception:
        pass


def _install_flush_on_exit(provider: Any) -> None:
    """Flush buffered spans on clean exit (atexit) and on SIGTERM (#O3).

    atexit does not run on ``kill``/container-stop, so a main-thread SIGTERM handler also
    flushes+shuts down. Both are guarded — tracing teardown must never raise.
    """
    flush = getattr(provider, "force_flush", None)
    if not callable(flush):
        return
    atexit.register(lambda: _safe(flush))
    if threading.current_thread() is threading.main_thread():
        try:
            prior = signal.getsignal(signal.SIGTERM)

            def _handler(signum: int, frame: Any) -> None:
                _safe(flush)
                _safe(getattr(provider, "shutdown", lambda: None))
                if callable(prior):
                    prior(signum, frame)

            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, OSError):  # pragma: no cover - not on main thread / unsupported
            pass


def _safe(fn: Any) -> None:
    try:
        fn()
    except Exception:
        pass


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
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]: ...


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
