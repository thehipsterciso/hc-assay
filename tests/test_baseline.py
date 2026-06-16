"""Baseline toolkit — determinism harness + numeric primitives (pure, offline)."""

import math

import pytest

from assay_engine.baseline.determinism import (
    build_baseline_artifact,
    corpus_fingerprint,
    hash_value,
    stable_seed,
)
from assay_engine.baseline.primitives import (
    cosine_similarity,
    cosine_similarity_matrix,
    descriptive_stats,
    euclidean_distance,
)
from assay_engine.contracts.schema import Corpus, Relation, Unit


# ---- determinism harness ----

def _corpus() -> Corpus:
    return Corpus(
        units=(Unit("a", "hello", {"k": 1}), Unit("b", "world")),
        relations=(Relation("a", "b", "rel"),),
        metadata={"v": 1},
    )


def test_corpus_fingerprint_is_order_independent_and_stable():
    c1 = Corpus(units=(Unit("a"), Unit("b")))
    c2 = Corpus(units=(Unit("b"), Unit("a")))  # different unit order
    assert corpus_fingerprint(c1) == corpus_fingerprint(c2)
    # content change -> different fingerprint
    assert corpus_fingerprint(c1) != corpus_fingerprint(Corpus(units=(Unit("a"), Unit("c"))))


def test_stable_seed_is_deterministic_and_distinct():
    assert stable_seed("x", "y") == stable_seed("x", "y")
    assert stable_seed("x", "y") != stable_seed("x", "z")
    assert 0 <= stable_seed("a") < (1 << 32)


def test_hash_value_canonical_and_order_independent():
    assert hash_value({"a": 1, "b": 2}) == hash_value({"b": 2, "a": 1})
    assert hash_value([1, 2]) != hash_value([2, 1])  # sequence order is significant


def test_build_artifact_records_full_determinism_and_is_reproducible():
    c = _corpus()
    a1 = build_baseline_artifact(c, {"sim": [[1.0]]}, component_versions={"builder": "demo@1"})
    a2 = build_baseline_artifact(c, {"sim": [[1.0]]}, component_versions={"builder": "demo@1"})
    assert a1.corpus_fingerprint == corpus_fingerprint(c)
    det = dict(a1.determinism)
    assert det["seed"] == dict(a2.determinism)["seed"]  # reproducible seed from same inputs
    assert det["input_hashes"]["corpus"] == corpus_fingerprint(c)
    assert det["component_versions"]["builder"] == "demo@1"
    assert "engine" in det["component_versions"] and "python" in det["component_versions"]
    assert hash(a1) is not None  # frozen + hashable (FrozenDict contents/determinism)


def test_build_artifact_extra_inputs_change_seed():
    c = _corpus()
    base = build_baseline_artifact(c, {}, extra_inputs={"cfg": {"alpha": 0.05}})
    other = build_baseline_artifact(c, {}, extra_inputs={"cfg": {"alpha": 0.01}})
    assert dict(base.determinism)["seed"] != dict(other.determinism)["seed"]
    assert "cfg" in dict(base.determinism)["input_hashes"]


# ---- primitives ----

def test_cosine_identical_orthogonal_opposite():
    assert cosine_similarity([1.0, 0.0], [2.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_zero_vector_is_zero_not_nan():
    sim = cosine_similarity([0.0, 0.0], [1.0, 1.0])
    assert sim == 0.0 and not math.isnan(sim)


def test_cosine_length_mismatch_raises():
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 2.0])


def test_euclidean_distance():
    assert euclidean_distance([0.0, 0.0], [3.0, 4.0]) == pytest.approx(5.0)


def test_cosine_matrix_symmetric_unit_diagonal():
    m = cosine_similarity_matrix([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    assert m[0][0] == pytest.approx(1.0)
    assert m[0][1] == pytest.approx(0.0)
    assert m[0][2] == pytest.approx(m[2][0])  # symmetric


def test_descriptive_stats():
    s = descriptive_stats([1.0, 2.0, 3.0, 4.0])
    assert s["mean"] == pytest.approx(2.5)
    assert s["median"] == pytest.approx(2.5)
    assert s["min"] == 1.0 and s["max"] == 4.0
    assert s["std"] == pytest.approx(math.sqrt(5.0 / 3.0))  # sample std (ddof=1)


def test_descriptive_stats_single_value_zero_std():
    s = descriptive_stats([7.0])
    assert s["std"] == 0.0 and s["mean"] == 7.0


def test_descriptive_stats_rejects_empty_and_nonfinite():
    with pytest.raises(ValueError):
        descriptive_stats([])
    with pytest.raises(ValueError):
        descriptive_stats([1.0, float("inf")])
