"""Tests for assay_engine.algorithms.similarity."""

import math

import pytest

from assay_engine.algorithms.similarity import (
    DistanceFn,
    SimilarityFn,
    canberra,
    chebyshev,
    cosine,
    distance_matrix,
    euclidean,
    hamming,
    jaccard,
    manhattan,
    minkowski,
    overlap_coefficient,
    pearson,
    similarity_matrix,
)


# ---------------------------------------------------------------------------
# cosine
# ---------------------------------------------------------------------------


class TestCosine:
    def test_identical(self) -> None:
        assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal(self) -> None:
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite(self) -> None:
        assert cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self) -> None:
        assert cosine([0.0, 0.0], [1.0, 1.0]) == pytest.approx(0.0)

    def test_clamped_to_valid_range(self) -> None:
        # Floating-point values can drift slightly outside [-1, 1]
        a = [1.0 + 1e-15] * 100
        result = cosine(a, a)
        assert -1.0 <= result <= 1.0

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            cosine([1.0], [1.0, 2.0])

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            cosine([], [])

    def test_protocol_compatible(self) -> None:
        def _sim(fn: SimilarityFn, a: list, b: list) -> float:
            return fn(a, b)

        assert _sim(cosine, [1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# pearson
# ---------------------------------------------------------------------------


class TestPearson:
    def test_perfectly_correlated(self) -> None:
        a = [1.0, 2.0, 3.0, 4.0]
        b = [2.0, 4.0, 6.0, 8.0]
        assert pearson(a, b) == pytest.approx(1.0)

    def test_perfectly_anticorrelated(self) -> None:
        a = [1.0, 2.0, 3.0]
        b = [3.0, 2.0, 1.0]
        assert pearson(a, b) == pytest.approx(-1.0)

    def test_constant_input_returns_zero(self) -> None:
        assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) == pytest.approx(0.0)

    def test_range(self) -> None:
        a = [1.0, 3.0, 5.0, 2.0, 4.0]
        b = [2.0, 1.0, 4.0, 3.0, 5.0]
        r = pearson(a, b)
        assert -1.0 <= r <= 1.0


# ---------------------------------------------------------------------------
# jaccard
# ---------------------------------------------------------------------------


class TestJaccard:
    def test_identical_binary(self) -> None:
        assert jaccard([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        assert jaccard([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_both_empty_sets(self) -> None:
        assert jaccard([0.0, 0.0], [0.0, 0.0]) == pytest.approx(1.0)

    def test_partial_overlap(self) -> None:
        result = jaccard([1.0, 1.0, 0.0], [1.0, 0.0, 1.0])
        assert result == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# overlap_coefficient
# ---------------------------------------------------------------------------


class TestOverlapCoefficient:
    def test_subset(self) -> None:
        # {0, 1} ⊆ {0, 1, 2} → overlap = 1.0
        assert overlap_coefficient([1.0, 1.0, 0.0], [1.0, 1.0, 1.0]) == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        assert overlap_coefficient([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_empty_set(self) -> None:
        assert overlap_coefficient([0.0, 0.0], [1.0, 1.0]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Distance measures
# ---------------------------------------------------------------------------


class TestEuclidean:
    def test_identical(self) -> None:
        assert euclidean([1.0, 2.0], [1.0, 2.0]) == pytest.approx(0.0)

    def test_unit_vectors(self) -> None:
        assert euclidean([1.0, 0.0], [0.0, 1.0]) == pytest.approx(math.sqrt(2))

    def test_triangle_inequality(self) -> None:
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        c = [0.0, 1.0]
        assert euclidean(a, c) <= euclidean(a, b) + euclidean(b, c) + 1e-10

    def test_protocol_compatible(self) -> None:
        def _dist(fn: DistanceFn, a: list, b: list) -> float:
            return fn(a, b)

        assert _dist(euclidean, [0.0], [1.0]) == pytest.approx(1.0)


class TestManhattan:
    def test_value(self) -> None:
        assert manhattan([1.0, 2.0], [4.0, 6.0]) == pytest.approx(7.0)

    def test_identical(self) -> None:
        assert manhattan([1.0, 2.0], [1.0, 2.0]) == pytest.approx(0.0)


class TestChebyshev:
    def test_value(self) -> None:
        assert chebyshev([1.0, 2.0, 3.0], [4.0, 0.0, 3.0]) == pytest.approx(3.0)

    def test_identical(self) -> None:
        assert chebyshev([1.0, 2.0], [1.0, 2.0]) == pytest.approx(0.0)


class TestMinkowski:
    def test_p1_equals_manhattan(self) -> None:
        a, b = [1.0, 2.0, 3.0], [4.0, 0.0, 3.0]
        assert minkowski(a, b, p=1.0) == pytest.approx(manhattan(a, b))

    def test_p2_equals_euclidean(self) -> None:
        a, b = [1.0, 2.0, 3.0], [4.0, 0.0, 3.0]
        assert minkowski(a, b, p=2.0) == pytest.approx(euclidean(a, b))

    def test_p_inf_equals_chebyshev(self) -> None:
        a, b = [1.0, 2.0, 3.0], [4.0, 0.0, 3.0]
        assert minkowski(a, b, p=math.inf) == pytest.approx(chebyshev(a, b))

    def test_p_below_1_raises(self) -> None:
        with pytest.raises(ValueError):
            minkowski([1.0], [2.0], p=0.5)


class TestHamming:
    def test_identical(self) -> None:
        assert hamming([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(0.0)

    def test_all_different(self) -> None:
        assert hamming([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)

    def test_half_different(self) -> None:
        assert hamming([1.0, 1.0, 0.0, 0.0], [1.0, 0.0, 1.0, 0.0]) == pytest.approx(0.5)


class TestCanberra:
    def test_identical(self) -> None:
        assert canberra([1.0, 2.0], [1.0, 2.0]) == pytest.approx(0.0)

    def test_both_zero_dimension_ignored(self) -> None:
        # When both x and y are 0 in a dimension, it contributes 0
        assert canberra([0.0, 1.0], [0.0, 2.0]) == pytest.approx(1 / 3)

    def test_nonnegative(self) -> None:
        assert canberra([1.0, -1.0], [2.0, -3.0]) >= 0.0


# ---------------------------------------------------------------------------
# Matrix utilities
# ---------------------------------------------------------------------------


class TestSimilarityMatrix:
    ROWS = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]

    def test_shape(self) -> None:
        mat = similarity_matrix(self.ROWS)
        assert len(mat) == 3
        assert all(len(row) == 3 for row in mat)

    def test_symmetric(self) -> None:
        mat = similarity_matrix(self.ROWS)
        for i in range(3):
            for j in range(3):
                assert mat[i][j] == pytest.approx(mat[j][i], abs=1e-10)

    def test_diagonal_self_similarity(self) -> None:
        mat = similarity_matrix(self.ROWS)
        for i in range(3):
            assert mat[i][i] == pytest.approx(1.0)

    def test_custom_fn(self) -> None:
        mat = similarity_matrix(self.ROWS, fn=pearson)
        assert len(mat) == 3


class TestDistanceMatrix:
    ROWS = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]

    def test_diagonal_zero(self) -> None:
        mat = distance_matrix(self.ROWS)
        for i in range(3):
            assert mat[i][i] == pytest.approx(0.0)

    def test_symmetric(self) -> None:
        mat = distance_matrix(self.ROWS)
        for i in range(3):
            for j in range(3):
                assert mat[i][j] == pytest.approx(mat[j][i], abs=1e-10)

    def test_custom_fn(self) -> None:
        mat = distance_matrix(self.ROWS, fn=manhattan)
        assert mat[0][1] == pytest.approx(1.0)
