"""Durable run-state checkpointer — local, data-sovereign (ADR-0003).

The orchestration graph persists its full state (current phase, gate decisions, locked
hypotheses, verdicts) through a checkpointer so a run can interrupt at a human-approval gate
and resume later. That state holds the entire analysis, so the store is **on-box only**
(ADR-0003); a SaaS checkpointer is disqualified.

This module is the LangGraph checkpointer factory, ported faithfully from the prior
platform's hardened implementation and generalized (dataset-agnostic ``ASSAY_*`` env, no
config-file coupling — see ADR-0006). The hardened behaviors are deliberately preserved
because each prevents a real production failure:

- a **self-healing ConnectionPool** (not a raw connection): when Postgres goes away — node
  sleep, restart, idle timeout, a network blip — a cached raw connection is permanently
  broken and every later checkpoint op raises, i.e. durability is lost exactly during the
  interrupt/resume the checkpointer exists to support. The pool runs a liveness check on
  checkout and replaces dead connections;
- a **session advisory lock** serializing first-time schema setup across *processes*, run on
  the *same* connection as the DDL (a pool would otherwise check out a different connection,
  leaving the lock ineffective);
- a **once-per-process-per-conn guard** (``setup()`` is idempotent but re-locking + replaying
  the migration query on every call is wasteful), with an in-process lock making the
  check-and-set atomic so concurrent threads don't both run setup;
- **credential redaction**: a backend exception (psycopg/psycopg_pool) can embed the full
  ``user:password`` URI/DSN in its own message, so the conn string is scrubbed precisely and
  the exception text via URI-userinfo + DSN-password backstops; the redacted message is then
  raised *outside* the exception handler, so the credential-bearing original is retained as
  neither ``__cause__`` nor ``__context__`` (a logger walking ``__context__`` cannot
  re-expose it);
- a single shared **atexit** pool-cleanup handler (one per process, not one per call) so the
  pool's worker thread is joined before interpreter finalization.

LangGraph/psycopg are optional (the ``persistence`` extra) and imported lazily; the
credential-redaction and connection-resolution logic is pure and unit-tested offline.
"""

from __future__ import annotations

import atexit
import os
import re
import threading
from typing import Any, cast
from urllib.parse import urlsplit

from assay_engine._local import require_local_uri

_DEFAULT_PG = "postgresql://localhost:5432/assay"

# Arbitrary fixed key for the Postgres session advisory lock that serializes checkpoint
# schema migrations across concurrent initializers. The value is irrelevant beyond being a
# stable per-logical-schema constant; "ASSY" as an int.
_MIGRATION_LOCK_KEY = 0x4153_5359

# Guards the process-local one-time-init bookkeeping. The PG advisory lock serializes DDL
# across PROCESSES; this lock makes the in-process check-and-set sequences (atexit
# registration, the initialized-conn set) atomic so two threads can't double-register or
# double-setup.
_init_lock = threading.Lock()

# Pools opened by the factory, closed once at process exit via a single shared atexit handler
# (registering one handler per call would accumulate handlers across repeated factory calls).
_OPEN_POOLS: list[Any] = []
_atexit_registered = False

# conn_strs whose schema bootstrap (advisory lock + setup() DDL) has already run in this
# process — bootstrap once per process per schema; the advisory lock still guards the
# first-time cross-process race.
_INITIALIZED_CONN_STRS: set[str] = set()

# Strips ``://user:password@`` (URI userinfo) from any URI-like substring. '/' is allowed
# inside the userinfo so a password containing '/' is still redacted; only '@' (the userinfo
# terminator) and whitespace bound the match.
_CREDS_RE = re.compile(r"://[^@\s]+@")
# Strips a libpq keyword/value DSN password token (``password=...`` / ``pgpassword=...``),
# handling quoted values that may contain spaces.
_DSN_PW_RE = re.compile(r"(?i)\b(password|pgpassword)\s*=\s*('[^']*'|\"[^\"]*\"|\S+)")


def _sanitize_conn_str(conn_str: str) -> str:
    """Return ``scheme://host[:port]/path`` with any ``user:password`` userinfo stripped.

    Robust to malformed userinfo: a password containing ``/``/``#`` makes ``urlsplit``'s
    ``.port`` raise ``ValueError`` on access, so the whole parse (including attribute access)
    is guarded and falls back to the generic userinfo-strip regex / a constant placeholder.
    """
    try:
        u = urlsplit(conn_str)
        host = u.hostname or ""
        port = u.port
        scheme = u.scheme
        path = u.path
    except ValueError:
        return _CREDS_RE.sub("://", conn_str)
    if not host:
        return _CREDS_RE.sub("://", conn_str) if scheme else "<store>"
    if ":" in host:  # IPv6 literal — urlsplit drops the brackets; restore them
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port else host
    return f"{scheme}://{netloc}{path}" if scheme else "<store>"


def redact_creds(text: str, conn_str: str = "") -> str:
    """Remove credentials a backend exception may embed in its message text.

    Layers, in order of precision:

    1. exact replacement of the known ``conn_str`` (handles any password characters, incl.
       ``/`` and spaces) — this is the precise layer and covers the real connection string;
    2. a generic URI-userinfo strip (``://user:pass@`` → ``://``) as a backstop for any
       *other* URI in the text;
    3. a libpq DSN ``password=``/``pgpassword=`` strip for the keyword/value form.

    Layers 2–3 are best-effort for *secondary* endpoints (e.g. a replica DSN) the caller did
    not pass as ``conn_str``; the primary connection string is always scrubbed precisely.
    """
    if conn_str:
        text = text.replace(conn_str, _sanitize_conn_str(conn_str))
    text = _CREDS_RE.sub("://", text)
    return _DSN_PW_RE.sub(r"\1=***", text)


def get_postgres_connection_string() -> str:
    """Resolve the Postgres connection string (``ASSAY_POSTGRES_URL`` env → loopback default).

    The env path bypasses any external config validation, so loopback is enforced here at the
    point of use (ADR-0003 defense-in-depth): graph state must not leave the box.
    """
    url = os.environ.get("ASSAY_POSTGRES_URL") or _DEFAULT_PG
    return require_local_uri(url, what="checkpointer connection")


def _safe_close(pool: Any) -> None:
    """Close one pool, swallowing errors so a single failing ``close()`` does not abort
    cleanup of the remaining pools at interpreter exit (``close()`` calls a C ``finish()``
    that can raise)."""
    try:
        pool.close()
    except Exception:
        pass


def _close_all_pools() -> None:
    for p in _OPEN_POOLS:
        _safe_close(p)


def _register_pool_cleanup(pool: Any) -> None:
    global _atexit_registered
    with _init_lock:
        _OPEN_POOLS.append(pool)
        if not _atexit_registered:
            atexit.register(_close_all_pools)
            _atexit_registered = True


def get_checkpointer(use_memory: bool = False) -> Any:
    """Return a configured LangGraph checkpointer.

    ``use_memory=True`` returns an in-memory saver (tests / no-Postgres). Otherwise a
    Postgres-backed saver over a self-healing pool, with advisory-locked one-time schema
    setup. Raises ``RuntimeError`` (with credentials redacted) if the backend is unreachable
    or the extra is not installed.
    """
    try:
        if use_memory:
            from langgraph.checkpoint.memory import MemorySaver

            return MemorySaver()
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "Postgres checkpointer requires the 'persistence' extra "
            "(langgraph-checkpoint-postgres, psycopg[binary,pool]) — not installed"
        ) from exc

    conn_str = get_postgres_connection_string()
    failure: str | None = None
    try:
        pool = ConnectionPool(
            conn_str,
            min_size=1,
            max_size=8,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            check=ConnectionPool.check_connection,  # liveness check on checkout (self-healing)
            open=True,
        )
        _register_pool_cleanup(pool)
        # Bootstrap the schema once per process per conn_str. The advisory lock and the DDL
        # must run on the SAME connection (pg_advisory_lock is session-scoped); a pool-backed
        # setup() would lock one connection and DDL on another, leaving the lock ineffective.
        with _init_lock:
            if conn_str not in _INITIALIZED_CONN_STRS:
                with pool.connection() as conn:
                    conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_KEY,))
                    try:
                        # row_factory=dict_row makes this connection dict-rowed at runtime
                        # (what PostgresSaver requires); the cast asserts that runtime truth
                        # the type system can't infer from the pool kwargs.
                        PostgresSaver(cast(Any, conn)).setup()  # DDL on the locked connection
                    finally:
                        # Best-effort unlock; the lock auto-releases when the connection
                        # returns to the pool, and raising here would mask a setup() error.
                        try:
                            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_KEY,))
                        except Exception:
                            pass
                _INITIALIZED_CONN_STRS.add(conn_str)
        return PostgresSaver(cast(Any, pool))  # dict-rowed pool (row_factory=dict_row)
    except Exception as exc:
        # Build the redacted message here, but raise it OUTSIDE the handler (below) so the
        # original — credential-bearing — exception is retained as neither __cause__ NOR
        # __context__ (a logger walking __context__ would otherwise re-expose the password).
        failure = (
            f"Postgres checkpointer connection failed (is Postgres running on "
            f"{_sanitize_conn_str(conn_str)}?): {redact_creds(str(exc), conn_str)}. "
            "For tests without Postgres, use get_checkpointer(use_memory=True)."
        )
    raise RuntimeError(failure)


def configured_checkpointer(use_memory: bool | None = None) -> Any:
    """Return the checkpointer the environment selects.

    ``use_memory`` (or ``ASSAY_CHECKPOINT_BACKEND=memory``) chooses the in-memory saver;
    otherwise Postgres.
    """
    if use_memory is None:
        use_memory = os.environ.get("ASSAY_CHECKPOINT_BACKEND", "postgres").lower() == "memory"
    return get_checkpointer(use_memory=use_memory)
