"""Data-sovereignty helper: enforce that network endpoints are loopback-only (ADR-0003).

Every engine component that takes a host/URL for an on-box service (local model runtime,
tracing collector, vector store, checkpoint database) routes it through here so a non-local
address fails loud rather than silently shipping data off the machine.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


class NonLocalEndpointError(RuntimeError):
    """Raised when a configured endpoint is not loopback (would leave the machine)."""


def is_loopback_host(host: str | None) -> bool:
    """True only for genuine loopback hosts.

    Parses the host as an IP and tests the loopback network (127.0.0.0/8, ::1), so a public
    name that merely *starts with* ``127.`` (e.g. ``127.0.0.1.evil.com``) is correctly
    rejected. The literal ``localhost`` is the only accepted non-IP host.
    """
    if not host:
        return False
    h = host.strip().lower()
    if h == "localhost":
        return True
    try:
        return ipaddress.ip_address(h.strip("[]")).is_loopback
    except ValueError:
        return False


def require_loopback_url(url: str, *, what: str) -> str:
    """Return ``url`` if its host is loopback; else raise :class:`NonLocalEndpointError`."""
    host = urlparse(url).hostname
    if not is_loopback_host(host):
        raise NonLocalEndpointError(
            f"{what} must be loopback-only (ADR-0003 data sovereignty); got host {host!r} "
            f"from {url!r}"
        )
    return url
