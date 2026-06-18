"""Tests for assay_engine.algorithms.anomaly."""

import pytest

from assay_engine.algorithms.anomaly import (
    AnomalyResult,
    iqr_detector,
    isolation_score,
    lof,
    mad_detector,
    zscore_detector,
)


CLEAN = [
    2.0,
    2.02,
    2.0,
    1.98,
    2.01,
    2.0,
    1.99,
    2.02,
    1.98,
    2.01,
    1.97,
    2.01,
    1.99,
    2.0,
    2.02,
    2.0,
    1.98,
    2.02,
    1.98,
    2.0,
]
WITH_OUTLIER = CLEAN + [100.0]


# ---------------------------------------------------------------------------
# zscore_detector
# ---------------------------------------------------------------------------


class TestZscoreDetector:
    def test_detects_outlier(self) -> None:
        result = zscore_detector(WITH_OUTLIER)
        assert result.outlier_flags[-1] is True

    def test_clean_data_no_outliers(self) -> None:
        result = zscore_detector(CLEAN)
        assert not any(result.outlier_flags)

    def test_result_type(self) -> None:
        result = zscore_detector(CLEAN)
        assert isinstance(result, AnomalyResult)

    def test_result_lengths_match_input(self) -> None:
        result = zscore_detector(WITH_OUTLIER)
        assert len(result.scores) == len(WITH_OUTLIER)
        assert len(result.outlier_flags) == len(WITH_OUTLIER)

    def test_n_outliers(self) -> None:
        result = zscore_detector(WITH_OUTLIER)
        assert result.n_outliers == 1

    def test_constant_input_no_outliers(self) -> None:
        result = zscore_detector([5.0] * 10)
        assert not any(result.outlier_flags)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            zscore_detector([])

    def test_custom_threshold(self) -> None:
        # With threshold=1.0 we should flag more points
        strict = zscore_detector(CLEAN + [5.0], threshold=1.0)
        lenient = zscore_detector(CLEAN + [5.0], threshold=3.0)
        assert strict.n_outliers >= lenient.n_outliers


# ---------------------------------------------------------------------------
# iqr_detector
# ---------------------------------------------------------------------------


class TestIQRDetector:
    def test_detects_outlier(self) -> None:
        result = iqr_detector(WITH_OUTLIER)
        assert result.outlier_flags[-1] is True

    def test_clean_no_outliers(self) -> None:
        result = iqr_detector(CLEAN)
        assert not any(result.outlier_flags)

    def test_scores_nonnegative(self) -> None:
        result = iqr_detector(WITH_OUTLIER)
        assert all(s >= 0.0 for s in result.scores)

    def test_inlier_score_zero(self) -> None:
        result = iqr_detector(WITH_OUTLIER)
        # First elements are clean inliers
        assert result.scores[0] == pytest.approx(0.0)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            iqr_detector([])

    def test_n_outliers_count(self) -> None:
        result = iqr_detector(WITH_OUTLIER)
        assert result.n_outliers == sum(result.outlier_flags)


# ---------------------------------------------------------------------------
# mad_detector
# ---------------------------------------------------------------------------


class TestMADDetector:
    def test_detects_outlier(self) -> None:
        result = mad_detector(WITH_OUTLIER)
        assert result.outlier_flags[-1] is True

    def test_clean_no_outliers(self) -> None:
        result = mad_detector(CLEAN)
        assert not any(result.outlier_flags)

    def test_constant_no_outliers(self) -> None:
        result = mad_detector([1.0] * 10)
        assert not any(result.outlier_flags)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            mad_detector([])


# ---------------------------------------------------------------------------
# LOF
# ---------------------------------------------------------------------------


class TestLOF:
    CLUSTER_A = [[1.0, 1.0], [1.1, 0.9], [0.9, 1.1], [1.0, 0.95]] * 3
    OUTLIER = [[50.0, 50.0]]

    def test_outlier_flagged(self) -> None:
        pts = self.CLUSTER_A + self.OUTLIER
        result = lof(pts, k=5, threshold=2.0)
        assert result.outlier_flags[-1] is True

    def test_cluster_members_clean(self) -> None:
        pts = self.CLUSTER_A + self.OUTLIER
        result = lof(pts, k=5, threshold=2.0)
        # At least most cluster members should be inliers
        cluster_flags = result.outlier_flags[: len(self.CLUSTER_A)]
        assert sum(cluster_flags) <= len(self.CLUSTER_A) // 2

    def test_scores_nonnegative(self) -> None:
        pts = self.CLUSTER_A + self.OUTLIER
        result = lof(pts, k=5)
        assert all(s >= 0.0 for s in result.scores)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            lof([], k=5)

    def test_k_too_large_raises(self) -> None:
        pts = [[0.0, 0.0], [1.0, 1.0]]
        with pytest.raises(ValueError):
            lof(pts, k=2)

    def test_result_type(self) -> None:
        pts = self.CLUSTER_A + self.OUTLIER
        result = lof(pts, k=5)
        assert isinstance(result, AnomalyResult)


# ---------------------------------------------------------------------------
# isolation_score
# ---------------------------------------------------------------------------


class TestIsolationScore:
    INLIERS = [float(i) for i in range(50)]

    def test_outlier_higher_score(self) -> None:
        values = self.INLIERS + [1000.0]
        result = isolation_score(values, n_trees=50, seed=0)
        # The extreme outlier should have a higher score than the median inlier
        median_score = sorted(result.scores)[len(result.scores) // 2]
        assert result.scores[-1] > median_score

    def test_scores_in_unit_interval(self) -> None:
        values = self.INLIERS + [1000.0]
        result = isolation_score(values, n_trees=50, seed=0)
        assert all(0.0 <= s <= 1.0 for s in result.scores)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            isolation_score([])

    def test_result_lengths(self) -> None:
        values = self.INLIERS
        result = isolation_score(values, n_trees=10, seed=0)
        assert len(result.scores) == len(values)
        assert len(result.outlier_flags) == len(values)
