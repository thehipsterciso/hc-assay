"""Deep-immutable, hashable mapping for the engine's frozen value records.

Many engine dataclasses are ``frozen=True`` and carry mapping fields (``evidence``,
``metadata``, ``attributes``, ``params``, ``assertion``, ``provenance``, ``contents``,
``determinism``). With a plain ``dict`` default two problems arise (audit pass 1, issue #7):

1. ``frozen=True`` auto-generates ``__hash__`` over all fields, so the instances *look*
   hashable but raise ``TypeError`` the moment they are hashed (a dict is unhashable).
2. ``frozen`` only blocks attribute rebinding; the contained dict stays mutable in place,
   so a "frozen" provenance record can be silently altered after construction.

:class:`FrozenDict` fixes both: it is an immutable :class:`~collections.abc.Mapping` and is
hashable. :func:`freeze` recursively converts nested mappings/sequences/sets so the whole
structure is immutable and hashable. Each affected dataclass normalizes its mapping fields
through :func:`freeze` in ``__post_init__`` (via ``object.__setattr__`` to satisfy frozen).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterator


class FrozenDict(Mapping[str, Any]):
    """An immutable, hashable mapping. Item assignment is impossible; hashing is stable."""

    __slots__ = ("_data", "_hash")

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        # Freeze values so a directly-constructed FrozenDict satisfies its own
        # immutable+hashable contract even from nested-mutable input (audit pass 3, issue #27).
        # freeze() is idempotent, so routing through freeze_mapping costs only one extra pass.
        self._data: dict[str, Any] = (
            {k: freeze(v) for k, v in data.items()} if data is not None else {}
        )
        self._hash: int | None = None

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenDict({self._data!r})"

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(frozenset(self._data.items()))
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self._data) == dict(other)
        return NotImplemented


def duck_mapping_items(value: Any) -> list[tuple[Any, Any]] | None:
    """Return ``(key, value)`` items if ``value`` is a dict-like NOT registered as a Mapping.

    A lazy/proxy dict-like (exposes ``keys()`` + ``__getitem__`` but is not a
    :class:`collections.abc.Mapping`) would otherwise be treated as an opaque, hashable-by-
    identity leaf by both :func:`freeze` and the measurement↔interpretation fence — passing
    through as a live mutable object and escaping the fence scan (#140). Returns ``None`` for
    anything that is not such a duck-typed mapping (incl. real Mappings, str/bytes, sequences).
    """
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return None
    keys = getattr(value, "keys", None)
    getitem = getattr(value, "__getitem__", None)
    if callable(keys) and callable(getitem):
        try:
            return [(k, value[k]) for k in keys()]
        except Exception:  # noqa: BLE001 — a misbehaving dict-like is not a usable mapping
            return None
    return None


def freeze(value: Any) -> Any:
    """Recursively convert ``value`` into an immutable, hashable form.

    Mappings → :class:`FrozenDict`, lists/tuples → tuples, sets → frozensets. Known mutable
    buffers are converted to hashable equivalents (``bytearray`` → ``bytes``;
    ``array.array`` / numpy-like arrays exposing ``tobytes`` → a ``(kind, shape, bytes)``
    tuple). Any remaining leaf that is not hashable raises ``TypeError`` *here, at
    construction time* — rather than silently passing through and resurfacing the error the
    moment the record is hashed (audit pass 2, issue #19; the incomplete half of #7).
    """
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        return FrozenDict({k: freeze(v) for k, v in value.items()})
    duck = duck_mapping_items(value)
    if duck is not None:  # lazy/proxy dict-like — freeze it like a mapping, not a leaf (#140)
        return FrozenDict({k: freeze(v) for k, v in duck})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze(v) for v in value)
    if isinstance(value, bytearray):
        return bytes(value)
    # Duck-typed buffer/array support (e.g. array.array, numpy.ndarray) without importing
    # numpy: an array-like exposing tobytes() is canonicalized to a hashable descriptor tuple.
    # Require an array-ish marker (shape/typecode/dtype) so an unrelated object that merely
    # happens to have a tobytes() is left to the hashability check below (fix-review nit, #19).
    tobytes = getattr(value, "tobytes", None)
    array_like = hasattr(value, "shape") or hasattr(value, "typecode") or hasattr(value, "dtype")
    if callable(tobytes) and array_like and not isinstance(value, (bytes, str)):
        shape = getattr(value, "shape", None)
        kind = getattr(getattr(value, "dtype", None), "str", None) or getattr(
            value, "typecode", type(value).__name__
        )
        # Route the descriptor through freeze() so a malformed tobytes() returning a
        # non-hashable value is still caught loud at construction (audit pass 3, issue #26).
        return freeze((str(kind), tuple(shape) if shape is not None else None, tobytes()))
    try:
        hash(value)
    except TypeError as exc:
        raise TypeError(
            f"freeze: leaf of type {type(value).__name__!r} is not hashable and has no "
            "known immutable conversion; a frozen value record cannot contain it"
        ) from exc
    return value


def freeze_mapping(value: Mapping[str, Any]) -> FrozenDict:
    """Normalize a mapping field to a deep-immutable :class:`FrozenDict`.

    Idempotent (pass 3, #F-034): an already-:class:`FrozenDict` value is returned unchanged so
    its lazily-cached hash survives. Re-wrapping (e.g. when ``ProvenanceEntry.__post_init__``
    freezes a payload that already holds FrozenDict values) would otherwise allocate a fresh
    FrozenDict with ``_hash=None`` and force an O(N·depth) re-hash on next use.
    """
    if isinstance(value, FrozenDict):
        return value
    return FrozenDict({k: freeze(v) for k, v in value.items()})


def unfreeze(value: Any) -> Any:
    """Recursively convert a frozen structure back into plain JSON-serializable containers.

    The inverse of :func:`freeze` for serialization: :class:`FrozenDict` → ``dict``,
    ``frozenset`` → sorted ``list`` (stable order for reproducible output), ``tuple`` →
    ``list``. Leaves are returned unchanged. ``json.dumps`` does not know :class:`FrozenDict`
    (it is a Mapping, not a ``dict`` subclass), so an operator serializing a deep-frozen public
    payload — e.g. ``GateReview.payload`` — must thaw it first (#141).
    """
    if isinstance(value, (FrozenDict, Mapping)):
        return {k: unfreeze(v) for k, v in value.items()}
    if isinstance(value, frozenset):
        # sort when elements are mutually orderable; otherwise keep insertion-free stable repr
        try:
            return [unfreeze(v) for v in sorted(value)]
        except TypeError:
            return [unfreeze(v) for v in value]
    if isinstance(value, (list, tuple)):
        return [unfreeze(v) for v in value]
    return value
