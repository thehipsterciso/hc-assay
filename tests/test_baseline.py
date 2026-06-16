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


def test_hash_value_is_type_faithful():
    # issue #B1: distinct keys sharing a str() must NOT collide
    assert hash_value({1: "a", "1": "b"}) != hash_value({1: "b", "1": "a"})
    # issue #B2: distinct values sharing a str() must NOT collide (no default=str coercion)
    import datetime

    assert hash_value(datetime.date(2020, 1, 1)) != hash_value("2020-01-01")
    assert hash_value(b"x") != hash_value("b'x'")
    # value type matters: int 1 vs str "1" vs float 1.0 vs bool True
    seen = {hash_value(1), hash_value("1"), hash_value(1.0), hash_value(True)}
    assert len(seen) == 4


def test_corpus_fingerprint_distinguishes_nonstr_key_attrs():
    # issue #B1 reached through the schema: numeric-keyed attributes must not collapse
    a = Corpus(units=(Unit("u", "t", {1: "alpha", "1": "beta"}),))
    b = Corpus(units=(Unit("u", "t", {1: "DIFFERENT", "1": "beta"}),))
    assert corpus_fingerprint(a) != corpus_fingerprint(b)


def test_hash_value_canonicalizes_known_faithful_types():
    import datetime

    # date is faithfully canonicalized and distinct from its string form
    assert hash_value(datetime.date(2020, 1, 1)) == hash_value(datetime.date(2020, 1, 1))
    assert hash_value(datetime.date(2020, 1, 1)) != hash_value(datetime.date(2020, 1, 2))


def test_hash_value_rejects_unreproducible_leaf():
    # issue #B5: an object with a default (address-based) repr would hash differently each
    # process — refuse loudly rather than poison the fingerprint
    class Weird:
        __slots__ = ()

    with pytest.raises(TypeError):
        hash_value({"k": Weird()})


def test_hash_value_rejects_non_finite_float():
    # issue #B4: NaN/inf must surface, not be encoded as JSON NaN/Infinity tokens
    with pytest.raises(ValueError):
        hash_value(float("nan"))
    with pytest.raises(ValueError):
        hash_value([1.0, float("inf")])


def test_build_artifact_reserves_corpus_input_key():
    # issue #B7: an extra input named "corpus" must not clobber the corpus fingerprint
    with pytest.raises(ValueError):
        build_baseline_artifact(_corpus(), {}, extra_inputs={"corpus": "x"})


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


def test_descriptive_stats_quantiles_match_linear_reference():
    # linear-interpolation reference for 10..50: q25=20, median=30, q75=40
    s = descriptive_stats([10.0, 20.0, 30.0, 40.0, 50.0])
    assert s["q25"] == pytest.approx(20.0)
    assert s["median"] == pytest.approx(30.0)
    assert s["q75"] == pytest.approx(40.0)
    # and for 1..7: q25 = 2.5
    assert descriptive_stats([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])["q25"] == pytest.approx(2.5)


def test_cosine_stays_in_unit_range_under_float_error():
    # issue #B3: self-similarity must be exactly within [-1, 1], never 1.0000000002
    v = [-0.04598, 0.73061, -0.47901, 0.61005, 0.09739]
    assert -1.0 <= cosine_similarity(v, v) <= 1.0
    m = cosine_similarity_matrix([v, [1.0, 2.0, 3.0, 4.0, 5.0]])
    for row in m:
        for x in row:
            assert -1.0 <= x <= 1.0
    assert m[0][0] == 1.0  # non-zero self-similarity is exactly 1.0


def test_cosine_matrix_numpy_and_pure_agree():
    # the vectorized and pure paths must agree within float tolerance (both clamp to [-1,1])
    import importlib.util

    from assay_engine.baseline.primitives import _cosine_matrix_pure

    rows = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [0.0, 0.0, 0.0], [-1.0, 0.5, 2.0]]
    pure = _cosine_matrix_pure(rows)
    public = cosine_similarity_matrix(rows)  # numpy path when numpy installed
    for rp, ru in zip(pure, public):
        for a, b in zip(rp, ru):
            assert a == pytest.approx(b, abs=1e-9)
    if importlib.util.find_spec("numpy") is not None:
        from assay_engine.baseline.primitives import _cosine_matrix_numpy

        npm = _cosine_matrix_numpy(rows)
        assert npm[2] == [0.0, 0.0, 0.0, 0.0]  # zero-vector row
        assert npm[0][0] == 1.0  # exact unit diagonal for non-zero row


def test_cosine_matrix_empty():
    assert cosine_similarity_matrix([]) == []


def test_cosine_matrix_scale_uses_fast_path():
    # guards against a regression to the pure O(n²·d) path at corpus scale: a 300x64 matrix
    # must compute correctly and (with numpy installed) effectively instantly.
    import importlib.util
    import time as _t

    if importlib.util.find_spec("numpy") is None:
        pytest.skip("numpy not installed — vectorized path unavailable")
    rng = [[float((i * 7 + j * 13) % 97) for j in range(64)] for i in range(300)]
    start = _t.perf_counter()
    m = cosine_similarity_matrix(rng)
    elapsed = _t.perf_counter() - start
    assert len(m) == 300 and len(m[0]) == 300
    assert m[0][0] == pytest.approx(1.0)  # non-zero self-similarity exact
    assert elapsed < 2.0  # numpy path; the pure path would take far longer at this size


def test_cosine_rejects_non_finite_inputs():
    # issue #B6: a non-finite component must raise, not be clamped to a false 1.0
    with pytest.raises(ValueError):
        cosine_similarity([float("inf"), 1.0], [1.0, 1.0])
    with pytest.raises(ValueError):
        cosine_similarity_matrix([[float("nan"), 0.0]])
    with pytest.raises(ValueError):
        euclidean_distance([float("inf")], [0.0])


def test_cosine_matrix_rejects_norm_overflow():
    # audit N1: finite inputs whose squared norm overflows must raise, not yield inf/inf sims
    pytest.importorskip("numpy")
    from assay_engine.baseline.primitives import _cosine_matrix_numpy

    with pytest.raises(ValueError, match="overflow"):
        _cosine_matrix_numpy([[1e200, 1e200], [1e200, -1e200]])


def test_cosine_matrix_array_matches_list_and_is_ndarray():
    # #106: the ndarray variant avoids nested-list boxing but agrees with the list form
    np = pytest.importorskip("numpy")
    from assay_engine.baseline.primitives import (
        cosine_similarity_matrix,
        cosine_similarity_matrix_array,
    )

    rows = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    arr = cosine_similarity_matrix_array(rows)
    assert isinstance(arr, np.ndarray) and arr.shape == (3, 3)
    assert arr.tolist() == cosine_similarity_matrix(rows)
    assert cosine_similarity_matrix_array([]).shape == (0, 0)


def test_freeze_keeps_ndarray_opaque_o1():
    # #107: a numpy array in baseline contents is frozen to a small (kind, shape, bytes)
    # descriptor — NOT a recursively tuple-ized cell-by-cell copy.
    np = pytest.importorskip("numpy")
    from assay_engine._frozen import freeze

    frozen = freeze(np.zeros((100, 100)))
    # descriptor form: a 3-tuple (kind, shape, frozen-bytes), not a 100-deep nested structure
    assert isinstance(frozen, tuple) and len(frozen) == 3
    assert frozen[1] == (100, 100)
