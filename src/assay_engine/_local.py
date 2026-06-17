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


def is_local_socket_path(host: str | None) -> bool:
    """True for a libpq Unix-domain-socket host — a leading-'/' absolute directory (#K-SEC-1).

    libpq accepts ``host=/var/run/postgresql`` (or the query form ``?host=/tmp``) to connect over
    a local Unix-domain socket — a connection that NEVER touches the network, so it is strictly
    more data-sovereign than the TCP loopback the guard already permits. A single leading '/' is a
    local path; a Windows UNC prefix (two leading separators, e.g. ``//server`` or ``/\\server``)
    resolves to a remote SMB share and must still be rejected.
    """
    if not host:
        return False
    h = host.strip()
    # A comma means libpq MULTI-HOST (e.g. "/tmp,evil.com") — never a single socket dir. Reject so
    # the leading-'/' check can't wave through an off-box host hidden after the comma (#K-SEC-9-1).
    # Callers split multi-host and validate each element; a leaf reaching here must be one host.
    if "," in h:
        return False
    return h.startswith("/") and not h.startswith("//") and not h.startswith("/\\")


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


def _authority_hosts(netloc: str) -> list[str]:
    """Every host in a URI authority, supporting libpq's comma-separated multi-host form.

    ``urlparse().hostname`` returns only the *first* host of a multi-host authority
    (``host1:port1,host2:port2``), so a remote second host would slip past a single-host
    check (audit #D3). Each host may carry its own ``:port`` and IPv6 hosts are bracketed.

    Userinfo is stripped at the **first** ``@`` — matching libpq, which (unlike ``urlparse``,
    which uses the last ``@``) treats the first ``@`` as the userinfo delimiter. A string like
    ``user@evil.com:5432@localhost`` is therefore read as host ``evil.com`` here, not
    ``localhost`` (audit #D5). Any host element still containing ``@`` after that is ambiguous
    and is returned verbatim so the caller's loopback check fails it closed.
    """
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]
    hosts: list[str] = []
    for part in netloc.split(","):
        p = part.strip()
        if not p:
            continue
        if p.startswith("["):  # [ipv6] or [ipv6]:port
            end = p.find("]")
            hosts.append(p[1:end] if end != -1 else p[1:])
        else:
            hosts.append(p.rsplit(":", 1)[0] if ":" in p else p)
    return hosts


def require_local_uri(uri: str, *, what: str) -> str:
    """Return ``uri`` if it is local (ADR-0003), else raise :class:`NonLocalEndpointError`.

    Three forms are recognized, validated against what the real client (libpq for postgres,
    urllib for http, sqlite for files) actually connects to — not merely what ``urlparse``
    reports, since the two can disagree:

    - **URI with an authority** (``scheme://host…`` or scheme-relative ``//host…``): *every*
      host in the authority must be loopback (incl. each of a comma-separated multi-host
      authority, #D3), AND any ``host``/``hostaddr`` query parameter that libpq would use to
      override the authority host (#D2). ``hostaddr`` is checked independently of ``host``.
    - **libpq keyword/value DSN** (no authority but ``key=value`` tokens): ``host``/``hostaddr``
      must be loopback, tolerating libpq's whitespace/quoting around ``=`` (#P1, #D1).
    - **bare path** (no authority, no ``=``): a local file/dir — but a Windows UNC path
      (``\\\\server\\share``) is rejected as remote.

    Inputs that cannot be parsed safely fail closed (rejected), never accepted.
    """
    try:
        parsed = urlparse(uri)
        netloc = parsed.netloc
        query = parsed.query
    except ValueError:
        # e.g. a malformed IPv6 authority — we cannot determine the host, so refuse.
        raise NonLocalEndpointError(
            f"{what}: endpoint could not be parsed safely; rejecting (ADR-0003)"
        ) from None

    if netloc:
        # A backslash never legitimately appears in a URI authority; a WHATWG-normalizing
        # client (e.g. some HTTP stacks) treats '\' as '/', so it could read a different host
        # than urlparse. Refuse rather than risk that differential (audit #D6, defense-in-depth).
        if "\\" in netloc:
            raise NonLocalEndpointError(
                f"{what}: backslash in URI authority is not permitted (ADR-0003); rejecting"
            )
        for h in _authority_hosts(netloc):
            # A residual '@' means the authority is ambiguous between this parser and libpq —
            # fail closed (audit #D5).
            if "@" in h or not is_loopback_host(h):
                raise NonLocalEndpointError(
                    f"{what} must be a local store (ADR-0003 data sovereignty); authority "
                    f"names non-loopback host {h!r}"
                )
        for key in ("host", "hostaddr"):
            for val in parse_qs(query).get(key, []):
                # libpq allows a COMMA-SEPARATED multi-host value; split and validate EVERY element
                # (#K-SEC-9-1) — else "/tmp,evil.com" slipped through because the whole string
                # looked like a socket path and the off-box host after the comma was never checked.
                for h in (p.strip() for p in val.split(",")):
                    if h and not is_loopback_host(h) and not is_local_socket_path(h):
                        raise NonLocalEndpointError(
                            f"{what} must be a local store (ADR-0003 data sovereignty); URI query "
                            f"{key}={h!r} points off-box"
                        )
        return uri

    if "=" in uri:  # libpq keyword/value DSN (no URI authority)
        for match in _DSN_TOKEN_RE.finditer(uri):
            if match.group(1).strip().lower() in {"host", "hostaddr"}:
                raw = match.group(2).strip().strip("'\"")
                # Split libpq's comma-separated multi-host and validate each element (#K-SEC-9-1).
                for h in (p.strip() for p in raw.split(",")):
                    if h and not is_loopback_host(h) and not is_local_socket_path(h):
                        raise NonLocalEndpointError(
                            f"{what} must be a local store (ADR-0003 data sovereignty); DSN names "
                            f"non-loopback host {h!r}"
                        )
        return uri

    stripped = uri.lstrip()
    # Windows treats ANY two leading separators (in any mix of '\' and '/') as a UNC prefix
    # to a remote SMB share — \\srv, //srv, /\srv, \/srv all resolve off-box (audit #D6).
    # (The pure '//host' form is already caught by the authority branch above; covering it
    # here too keeps the branch self-contained.)
    if len(stripped) >= 2 and stripped[0] in "\\/" and stripped[1] in "\\/":
        raise NonLocalEndpointError(
            f"{what} must be a local store (ADR-0003 data sovereignty); UNC-style path "
            f"{uri!r} is a remote share"
        )
    return uri  # bare path / dir store
