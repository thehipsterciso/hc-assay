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


def require_loopback_host(host: str, *, what: str) -> str:
    """Return ``host`` if it is loopback; else raise. (``0.0.0.0`` binds all interfaces and
    is correctly rejected — it would expose data off-box.)"""
    if not is_loopback_host(host):
        raise NonLocalEndpointError(
            f"{what} must be a loopback host (ADR-0003 data sovereignty); got {host!r}"
        )
    return host


def require_local_uri(uri: str, *, what: str) -> str:
    """Return ``uri`` if it is local (ADR-0003), else raise :class:`NonLocalEndpointError`.

    Three forms are recognized:

    - **URI with a host component** (``scheme://host…`` or scheme-relative ``//host…``): the
      host must be loopback. A networked host smuggled into a ``sqlite://host`` or ``//host``
      spelling is rejected; a host-less ``sqlite:///file`` or ``file:///path`` is local.
    - **libpq keyword/value DSN** (no URI host but contains ``key=value`` tokens, e.g.
      ``host=db port=5432 dbname=x``): the ``host``/``hostaddr`` token must be loopback. This
      form has no ``://`` and would otherwise slip past a URI-only check (audit issue #P1).
    - **bare path** (no URI host, no ``=``): a local file/dir — local.
    """
    host = (urlparse(uri).hostname or "").strip()
    if host:
        if not is_loopback_host(host):
            raise NonLocalEndpointError(
                f"{what} must be a local store (ADR-0003 data sovereignty); got host {host!r}"
            )
        return uri
    if "=" in uri:  # libpq keyword/value DSN (no URI host component)
        for token in uri.split():
            key, sep, val = token.partition("=")
            if sep and key.strip().lower() in {"host", "hostaddr"}:
                h = val.strip().strip("'\"")
                if h and not is_loopback_host(h):
                    raise NonLocalEndpointError(
                        f"{what} must be a local store (ADR-0003 data sovereignty); DSN names "
                        f"non-loopback host {h!r}"
                    )
        return uri
    return uri  # bare path / dir store
