"""Parse numeric env vars with an error that NAMES the offending var (#H-022/#CV-S-1/#P9-MO-2).

A bare ``int(os.environ[...])`` / ``float(...)`` raises an opaque "invalid literal for int()" that
names neither the variable nor where it fired (usually at import, before any handler). These
helpers fall back to ``default`` (treating an empty value as unset) and, on a malformed value,
raise a ``ValueError`` naming the variable — the single source replacing the per-module copies that
had grown in ``observability/tracing.py`` and ``persistence/vectorstore.py``.
"""

from __future__ import annotations

import os


def _raw(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val if val is not None and val != "" else default


def int_env(name: str, default: str) -> int:
    raw = _raw(name, default)
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be an integer; got {raw!r}") from exc


def float_env(name: str, default: str) -> float:
    raw = _raw(name, default)
    try:
        return float(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a number; got {raw!r}") from exc
