"""Frozen value records are deeply immutable AND hashable (audit pass 1, issue #7)."""

import pytest

from assay_engine._frozen import FrozenDict, freeze, freeze_mapping, unfreeze
from assay_engine.contracts.schema import Unit
from assay_engine.methodology.verdict import Verdict, VerdictLabel


def test_frozendict_is_immutable_and_hashable():
    fd = FrozenDict({"a": 1, "b": 2})
    assert fd["a"] == 1 and len(fd) == 2
    assert hash(fd) == hash(FrozenDict({"b": 2, "a": 1}))  # order-independent
    with pytest.raises(TypeError):
        fd["a"] = 9  # type: ignore[index]


def test_freeze_is_recursive():
    frozen = freeze({"x": {"y": [1, 2]}, "s": {3, 4}})
    assert isinstance(frozen["x"], FrozenDict)
    assert frozen["x"]["y"] == (1, 2)
    assert isinstance(frozen["s"], frozenset)
    assert hash(frozen) is not None  # fully hashable


def test_freeze_mapping_returns_frozendict():
    assert isinstance(freeze_mapping({"k": "v"}), FrozenDict)


def test_freeze_mapping_is_idempotent_and_preserves_cached_hash():
    # #F-034: re-freezing an already-FrozenDict must return the SAME object so its lazily-cached
    # hash survives — re-wrapping would allocate a fresh FrozenDict with _hash=None and force an
    # O(N*depth) re-hash. (ProvenanceEntry/DeterminismRecord re-freeze payloads that already hold
    # FrozenDict values.)
    fd = freeze_mapping({"a": 1, "nested": {"b": 2}})
    _ = hash(fd)  # populate the cache
    assert fd._hash is not None
    again = freeze_mapping(fd)
    assert again is fd  # same object, not a rebuilt copy
    assert again._hash is fd._hash  # cached hash preserved


def test_unfreeze_frozenset_of_unorderable_types_is_deterministic():
    # #G-004: unfreeze sorts a frozenset for reproducible output; for unorderable mixed types it
    # must fall back to a STABLE key (type name, repr), NOT raw set iteration order (hash-seed
    # dependent → non-reproducible across processes). By (type name, repr), ints precede strs.
    assert unfreeze(frozenset({1, "a", 2, "b"})) == [1, 2, "a", "b"]
    assert unfreeze(frozenset({"b", 2, "a", 1})) == [1, 2, "a", "b"]


def test_unfreeze_frozenset_order_is_seed_independent_subprocess():
    # #G-004 (deterministic discrimination): the in-process assertion above can pass ~1/3 of the
    # time even on the buggy raw-iteration code because CPython's per-process hash seed sometimes
    # coincides with the stable order. Pin PYTHONHASHSEED to a value at which raw set-iteration
    # order is known to DIFFER from the stable order, run in a subprocess, and assert the stable
    # output — so a revert to raw iteration fails this guard EVERY run, not probabilistically.
    import os
    import subprocess
    import sys

    snippet = (
        "from assay_engine._frozen import unfreeze;"
        "assert unfreeze(frozenset({1,'a',2,'b'})) == [1,2,'a','b'], 'non-deterministic order'"
    )
    # seed where raw frozenset iteration of {1,'a',2,'b'} is ['b',1,2,'a'] (verified) — i.e. it
    # DIFFERS from the stable [1,2,'a','b'], so the reverted raw-iteration code fails this every run.
    env = {**os.environ, "PYTHONHASHSEED": "2"}
    proc = subprocess.run([sys.executable, "-c", snippet], env=env, capture_output=True, text=True)
    assert proc.returncode == 0, f"seed-independent order guard failed: {proc.stderr}"


def test_verdict_is_hashable_and_evidence_immutable():
    v = Verdict("h", VerdictLabel.SUPPORTED, "rule", evidence={"p_value": 0.01})
    assert hash(v) is not None  # no longer TypeError
    assert isinstance(v.evidence, FrozenDict)
    with pytest.raises(TypeError):
        v.evidence["p_value"] = 0.99  # type: ignore[index]


def test_unit_attributes_cannot_be_mutated_in_place():
    u = Unit("a", attributes={"k": "v"})
    with pytest.raises(TypeError):
        u.attributes["k"] = "x"  # type: ignore[index]
    assert hash(u) is not None


# ---- issue #19: freeze honors its hashable contract on leaves ----


def test_freeze_converts_bytearray_to_bytes():
    frozen = freeze({"b": bytearray(b"xy")})
    assert frozen["b"] == b"xy"
    assert hash(frozen) is not None


def test_freeze_canonicalizes_array_buffer():
    import array

    frozen = freeze({"a": array.array("d", [1.0, 2.0])})
    assert hash(frozen) is not None  # array.array would otherwise be unhashable


def test_freeze_raises_loud_on_unhashable_unconvertible_leaf():
    class Unhashable:
        __hash__ = None  # type: ignore[assignment]

    with pytest.raises(TypeError):
        freeze({"x": Unhashable()})


def test_baseline_artifact_with_buffer_contents_is_hashable():
    import array

    from assay_engine.baseline.toolkit import BaselineArtifact

    ba = BaselineArtifact(corpus_fingerprint="fp", contents={"emb": array.array("d", [1.0])})
    assert hash(ba) is not None  # was a latent TypeError before #19


def test_freeze_array_like_with_bad_tobytes_raises_at_construction():
    # issue #26: a malformed array-like whose tobytes() returns an unhashable, unconvertible
    # value must be caught loud at construction, not deferred to hash time. (A bytearray
    # result is fine — freeze converts it to bytes — so use a genuinely unconvertible one.)
    class BadResult:
        __hash__ = None  # type: ignore[assignment]

    class Weird:
        typecode = "d"

        def tobytes(self):
            return BadResult()

    with pytest.raises(TypeError):
        freeze(Weird())


def test_frozendict_direct_construction_is_deeply_immutable_and_hashable():
    # issue #27: building FrozenDict directly from nested mutable input still honors contract
    fd = FrozenDict({"a": {"b": 1}, "c": [1, 2]})
    assert isinstance(fd["a"], FrozenDict)
    assert fd["c"] == (1, 2)
    assert hash(fd) is not None
    assert fd == freeze({"a": {"b": 1}, "c": [1, 2]})
