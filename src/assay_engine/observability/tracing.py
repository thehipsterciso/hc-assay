"""Self-hosted tracing seam (contract + stub).

OpenTelemetry → on-box collector. The engine emits spans through this seam so the concrete
exporter (loopback-bound local collector) can be configured once and enforced everywhere.
Lifted from the prior platform; loopback enforcement and credential scrubbing carry over.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable


@runtime_checkable
class Tracer(Protocol):
    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        ...


class NoopTracer:
    """A tracer that records nothing — default until the local collector is wired."""

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        yield
