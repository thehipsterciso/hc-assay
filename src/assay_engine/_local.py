"""Data-sovereignty helper: enforce that network endpoints are loopback-only (ADR-0003).

Every engine component that takes a host/URL for an on-box service (local model runtime,
tracing collector, vector store, checkpoint database) routes it through here so a non-local
address fails loud rather than silently shipping data off the machine.
"""

from __future__ import annotations

from urllib.parse import urlparse

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


class NonLocalEndpointError(RuntimeError):
    """Raised when a configured endpoint is not loopback (would leave the machine)."""


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    h = host.strip().lower()
    if h in _LOOPBACK_HOSTS:
        return True
    # 127.0.0.0/8 is entirely loopback
    return h.startswith("127.")


def require_loopback_url(url: str, *, what: str) -> str:
    """Return ``url`` if its host is loopback; else raise :class:`NonLocalEndpointError`."""
    host = urlparse(url).hostname
    if not is_loopback_host(host):
        raise NonLocalEndpointError(
            f"{what} must be loopback-only (ADR-0003 data sovereignty); got host {host!r} "
            f"from {url!r}"
        )
    return url
