"""Durable checkpointer — local, data-sovereign run-state persistence (ADR-0003).

Two layers, ported and generalized from the prior platform's hardened checkpointer:

- a small :class:`Checkpointer` Protocol for engine-level phase-state persistence;
- the LangGraph checkpointer factory the orchestration graph uses, with the hardened
  connection handling: loopback-enforced connection string, **credential redaction** so a
  backend exception never leaks ``user:password``, a self-healing pool, and advisory-locked
  one-time schema setup.

LangGraph/psycopg are optional (the ``persistence`` extra) and imported lazily; the
credential-redaction and connection-resolution logic is pure and unit-tested offline.
"""

from __future__ import annotations

import os
import re
from typing import Any, Mapping, Protocol, runtime_checkable
from urllib.parse import urlparse

from assay_engine._local import require_local_uri

_DEFAULT_PG = "postgresql://localhost:5432/assay"
# Strip URI userinfo (user:pass@) as a generic backstop.
_CREDS_RE = re.compile(r"://[^@\s]+@")


@runtime_checkable
class Checkpointer(Protocol):
    def save(self, run_id: str, phase: str, state: Mapping[str, Any]) -> None: ...
    def load(self, run_id: str) -> Mapping[str, Any] | None: ...


def _sanitize_conn_str(conn_str: str) -> str:
    """Return ``scheme://host[:port]/path`` with any userinfo removed (IPv6 re-bracketed).

    Robust to malformed userinfo: a password containing ``/`` or ``#`` makes ``urlparse``'s
    ``.port`` raise ``ValueError`` on access, so the whole parse (incl. attribute access) is
    guarded and falls back to the generic userinfo-strip regex.
    """
    try:
        u = urlparse(conn_str)
        host = u.hostname
        port = u.port
        scheme = u.scheme
        path = u.path
    except ValueError:
        return _CREDS_RE.sub("://", conn_str)
    if not host:
        return _CREDS_RE.sub("://", conn_str)
    host_b = f"[{host}]" if ":" in host else host
    netloc = host_b if port is None else f"{host_b}:{port}"
    return f"{scheme}://{netloc}{path}"


def redact_creds(text: str, conn_str: str = "") -> str:
    """Remove credentials a backend exception may embed in its message.

    Two layers: an exact replacement of the known ``conn_str`` (handles any password
    characters, incl. ``/`` and spaces), then a generic URI-userinfo strip as a backstop.
    """
    if conn_str:
        text = text.replace(conn_str, _sanitize_conn_str(conn_str))
    return _CREDS_RE.sub("://", text)


def get_postgres_connection_string() -> str:
    """Resolve the Postgres connection string (env override → default), enforced loopback.

    The env-var path bypasses any config-load validation, so it is guarded here too
    (point-of-use defense-in-depth). Graph state holds the full analysis and must not leave
    the box (ADR-0003).
    """
    url = os.environ.get("ASSAY_POSTGRES_URL") or _DEFAULT_PG
    return require_local_uri(url, what="checkpointer connection")


def configured_checkpointer(use_memory: bool | None = None) -> Any:
    """Return the LangGraph checkpointer the platform asks for (lazy import).

    ``use_memory`` (or ``ASSAY_CHECKPOINT_BACKEND=memory``) selects an in-memory saver for
    tests; otherwise a Postgres-backed saver. Credentials are redacted from any setup error.
    """
    if use_memory is None:
        use_memory = os.environ.get("ASSAY_CHECKPOINT_BACKEND", "postgres").lower() == "memory"
    try:
        if use_memory:
            from langgraph.checkpoint.memory import MemorySaver

            return MemorySaver()
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "checkpointer requires the 'persistence' extra (langgraph-checkpoint-postgres, "
            "psycopg) — not installed"
        ) from exc

    conn_str = get_postgres_connection_string()
    try:
        saver = PostgresSaver.from_conn_string(conn_str)
        saver.setup()
        return saver
    except Exception as exc:  # redact creds before the error is ever logged/raised
        raise RuntimeError(
            f"failed to initialize Postgres checkpointer: {redact_creds(str(exc), conn_str)}"
        ) from None
