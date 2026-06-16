"""Data-sovereignty helper: enforce that network endpoints are loopback-only (ADR-0003).

Every engine component that takes a host/URL for an on-box service (local model runtime,
tracing collector, vector store, checkpoint database) routes it through here so a non-local
address fails loud rather than silently shipping data off the machine.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qs, urlparse

# A libpq keyword/value token: ``key = value`` with optional whitespace around ``=`` (libpq
# permits it) and an optionally single/double-quoted value (which may contain spaces).
_DSN_TOKEN_RE = re.compile(r"(\w+)\s*=\s*('[^']*'|\"[^\"]*\"|\S+)")


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
    parsed = urlparse(uri)
    host = (parsed.hostname or "").strip()
    if host:
        if not is_loopback_host(host):
            raise NonLocalEndpointError(
                f"{what} must be a local store (ADR-0003 data sovereignty); got host {host!r}"
            )
        # A libpq URI lets a query parameter host=/hostaddr= OVERRIDE the authority host —
        # urlparse only sees the authority, so the query must be checked too or a remote
        # endpoint slips past while the parser reports "local" (audit #D2). hostaddr is the
        # literal IP libpq dials and must be checked independently of host.
        query = parse_qs(parsed.query)
        for key in ("host", "hostaddr"):
            for val in query.get(key, []):
                h = val.strip()
                if h and not is_loopback_host(h):
                    raise NonLocalEndpointError(
                        f"{what} must be a local store (ADR-0003 data sovereignty); URI query "
                        f"{key}={h!r} points off-box"
                    )
        return uri
    if "=" in uri:  # libpq keyword/value DSN (no URI host component)
        # Whitespace is permitted around '=' in libpq DSNs (e.g. "host = db.evil.com"), so a
        # naive token split misses the host value — a real tokenizer is required (audit #D1).
        for match in _DSN_TOKEN_RE.finditer(uri):
            if match.group(1).strip().lower() in {"host", "hostaddr"}:
                h = match.group(2).strip().strip("'\"")
                if h and not is_loopback_host(h):
                    raise NonLocalEndpointError(
                        f"{what} must be a local store (ADR-0003 data sovereignty); DSN names "
                        f"non-loopback host {h!r}"
                    )
        return uri
    return uri  # bare path / dir store
