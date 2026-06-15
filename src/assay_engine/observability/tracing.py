"""Self-hosted tracing seam (contract + stub).

OpenTelemetry → on-box collector. The engine emits spans through this seam so the concrete
exporter (loopback-bound local collector) can be configured once and enforced everywhere.
When the concrete tracer is lifted from the prior platform, loopback enforcement and
credential scrubbing will be enforced in that implementation — NOT here, where only the
Protocol and a fail-loud placeholder live (audit pass 1, issue #14).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable


@runtime_checkable
class Tracer(Protocol):
    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        ...


class UnconfiguredTracer:
    """Placeholder until the local collector is wired. Fails loud rather than silently
    dropping spans (and providing none of the loopback/scrubbing guarantees of the real
    tracer). Tests that need a no-op should supply their own explicit double."""

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        raise NotImplementedError(
            "tracing seam not yet wired — port the self-hosted OpenTelemetry tracer "
            "(loopback-bound local collector + credential scrubbing, ADR-0003)"
        )
        yield  # pragma: no cover - unreachable; keeps this a generator/contextmanager
