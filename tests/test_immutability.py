"""Frozen value records are deeply immutable AND hashable (audit pass 1, issue #7)."""

import pytest

from assay_engine._frozen import FrozenDict, freeze, freeze_mapping
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
