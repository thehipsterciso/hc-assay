"""Type-faithful canonical hashing — the engine's single content-digest primitive.

Two unrelated places need a *stable, type-faithful* content hash: the baseline determinism
harness (so the same inputs reproduce the same baseline) and pre-registration (so a lock
binds the exact hypothesis content). Both must distinguish values that merely share a
``str()`` — ``int 1`` from ``str "1"``, ``date(2020,1,1)`` from ``"2020-01-01"`` — or the
hash is a liability rather than a guarantee.

This module is the one implementation, hoisted here so it sits *below* both
``methodology`` and ``baseline`` in the import graph (neither may depend on the other). It is
dependency-free and pure. Anything it cannot canonicalize reproducibly is refused **loudly**:
a default (address-based) ``repr`` would make the digest differ every process and silently
break the guarantee it exists to provide.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import hashlib
import json
import uuid
from typing import Any, Mapping


def keytag(key: Any) -> str:
    """A type-faithful, sortable string for a mapping key, so distinct keys that happen to
    share a ``str()`` (e.g. int ``1`` vs str ``"1"``) do NOT collide."""
    return f"{type(key).__name__}::{key!r}"


def canonical_plain(value: Any) -> Any:
    """Canonicalize ``value`` into a fully JSON-native, type-faithful structure for hashing.

    Mappings become a sorted list of ``[typed-key, value]`` pairs; bytes, sets, and any
    non-JSON-native leaf are tagged with their type rather than stringified. Nothing is coerced
    with ``str()``, so the content hash distinguishes values that share a ``str()``.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value  # JSON-native scalars; json encodes 1, "1", true, 1.0 distinctly
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, Mapping):
        pairs = sorted(
            ([keytag(k), canonical_plain(v)] for k, v in value.items()), key=lambda p: p[0]
        )
        return {"__map__": pairs}
    if isinstance(value, (list, tuple)):
        return [canonical_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((canonical_plain(v) for v in value), key=repr)}
    # A small allowlist of leaf types with a value-faithful canonical form.
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return {"__temporal__": value.isoformat()}
    if isinstance(value, decimal.Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, uuid.UUID):
        return {"__uuid__": str(value)}
    # Anything else is refused LOUDLY rather than repr-tagged: a default (address-based) repr
    # would make the digest differ every process, silently breaking the guarantee.
    raise TypeError(
        f"cannot canonicalize a leaf of type "
        f"{type(value).__module__}.{type(value).__qualname__!r} reproducibly — convert it to a "
        "JSON-native value, bytes, date/datetime/Decimal/UUID before hashing"
    )


def canonical_json(value: Any) -> str:
    """The canonical JSON text of ``value`` — stable across processes and key orderings."""
    return json.dumps(canonical_plain(value), sort_keys=True, allow_nan=False)


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_value(value: Any) -> str:
    """Stable, type-faithful content hash of an arbitrary value.

    ``canonical_plain`` canonicalizes everything to JSON-native form first, so ``json.dumps``
    needs no ``default=`` coercion — anything it still cannot encode is a real bug to surface,
    not to silently stringify.
    """
    return hash_text(canonical_json(value))
