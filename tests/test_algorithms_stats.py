"""Tests for assay_engine.algorithms.stats."""

import math

import pytest

from assay_engine.algorithms.stats import (
    SummaryStats,
    Summarizer,
    describe,
    entropy,
    geometric_mean,
    harmonic_mean,
    quantile,
    robust_z_scores,
    trim_mean,
    winsorise,
    z_scores,
)


# ---------------------------------------------------------------------------
# describe / SummaryStats
# ---------------------------------------------------------------------------


class TestDescribe:
    VALUES = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]

    def test_n(self) -> None:
        s = describe(self.VALUES)
        assert s.n == 8

    def test_mean(self) -> None:
        s = describe(self.VALUES)
        assert s.mean == pytest.approx(5.0)

    def test_variance(self) -> None:
        s = describe(self.VALUES)
        # sample variance ddof=1: sum((x-5)^2)/7 = 32/7
        assert s.variance == pytest.approx(32 / 7, rel=1e-6)

    def test_std(self) -> None:
        s = describe(self.VALUES)
        assert s.std == pytest.approx((32 / 7) ** 0.5, rel=1e-6)

    def test_minimum(self) -> None:
        s = describe(self.VALUES)
        assert s.minimum == pytest.approx(2.0)

    def test_maximum(self) -> None:
        s = describe(self.VALUES)
        assert s.maximum == pytest.approx(9.0)

    def test_median(self) -> None:
        s = describe(self.VALUES)
        assert s.median == pytest.approx(4.5)

    def test_iqr(self) -> None:
        s = describe(self.VALUES)
        assert s.iqr == pytest.approx(s.q75 - s.q25)

    def test_symmetric_skewness(self) -> None:
        s = describe([1.0, 2.0, 3.0, 4.0, 5.0])
        assert s.skewness == pytest.approx(0.0, abs=1e-10)

    def test_single_element(self) -> None:
        s = describe([42.0])
        assert s.n == 1
        assert s.mean == 42.0
        assert s.variance == 0.0
        assert s.std == 0.0
        assert s.skewness == 0.0
        assert s.kurtosis == 0.0

    def test_two_elements(self) -> None:
        s = describe([1.0, 3.0])
        assert s.mean == pytest.approx(2.0)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            describe([])

    def test_result_type(self) -> None:
        s = describe(self.VALUES)
        assert isinstance(s, SummaryStats)

    def test_mad_nonnegative(self) -> None:
        s = describe(self.VALUES)
        assert s.mad >= 0.0

    def test_protocol_compatible(self) -> None:
        def _run(fn: Summarizer, vals: list) -> SummaryStats:
            return fn(vals)

        s = _run(describe, self.VALUES)
        assert s.n == len(self.VALUES)


# ---------------------------------------------------------------------------
# quantile
# ---------------------------------------------------------------------------


class TestQuantile:
    def test_minimum_p0(self) -> None:
        assert quantile([1.0, 2.0, 3.0], 0.0) == pytest.approx(1.0)

    def test_maximum_p1(self) -> None:
        assert quantile([1.0, 2.0, 3.0], 1.0) == pytest.approx(3.0)

    def test_median_p05(self) -> None:
        assert quantile([1.0, 2.0, 3.0], 0.5) == pytest.approx(2.0)

    def test_interpolation(self) -> None:
        result = quantile([0.0, 1.0], 0.25)
        assert result == pytest.approx(0.25)

    def test_invalid_p_raises(self) -> None:
        with pytest.raises(ValueError):
            quantile([1.0], 1.5)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            quantile([], 0.5)


# ---------------------------------------------------------------------------
# z_scores
# ---------------------------------------------------------------------------


class TestZScores:
    def test_mean_zero(self) -> None:
        zs = z_scores([1.0, 2.0, 3.0])
        assert abs(sum(zs)) < 1e-10

    def test_std_one(self) -> None:
        import math

        zs = z_scores([1.0, 2.0, 3.0, 4.0, 5.0])
        variance = sum(z**2 for z in zs) / (len(zs) - 1)
        assert math.sqrt(variance) == pytest.approx(1.0, abs=1e-9)

    def test_constant_input(self) -> None:
        zs = z_scores([5.0] * 5)
        assert zs == [0.0] * 5

    def test_empty_returns_empty(self) -> None:
        assert z_scores([]) == []

    def test_length_preserved(self) -> None:
        vals = [1.0, 2.0, 3.0, 4.0]
        assert len(z_scores(vals)) == len(vals)


# ---------------------------------------------------------------------------
# robust_z_scores
# ---------------------------------------------------------------------------


class TestRobustZScores:
    def test_outlier_flagged(self) -> None:
        vals = [2.0, 2.1, 1.9, 2.0, 2.05, 100.0]
        rzs = robust_z_scores(vals)
        # The outlier should have the largest absolute robust z-score
        assert abs(rzs[-1]) == max(abs(z) for z in rzs)

    def test_constant_returns_zeros(self) -> None:
        assert robust_z_scores([3.0] * 5) == [0.0] * 5

    def test_empty_returns_empty(self) -> None:
        assert robust_z_scores([]) == []

    def test_length_preserved(self) -> None:
        vals = [1.0, 2.0, 3.0]
        assert len(robust_z_scores(vals)) == len(vals)


# ---------------------------------------------------------------------------
# geometric_mean
# ---------------------------------------------------------------------------


class TestGeometricMean:
    def test_basic(self) -> None:
        assert geometric_mean([1.0, 10.0, 100.0]) == pytest.approx(10.0)

    def test_identical_values(self) -> None:
        assert geometric_mean([4.0, 4.0, 4.0]) == pytest.approx(4.0)

    def test_nonpositive_raises(self) -> None:
        with pytest.raises(ValueError):
            geometric_mean([1.0, 0.0, 2.0])

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            geometric_mean([])


# ---------------------------------------------------------------------------
# harmonic_mean
# ---------------------------------------------------------------------------


class TestHarmonicMean:
    def test_basic(self) -> None:
        # HM(1, 2) = 2 / (1 + 0.5) = 4/3
        assert harmonic_mean([1.0, 2.0]) == pytest.approx(4 / 3)

    def test_identical(self) -> None:
        assert harmonic_mean([5.0, 5.0]) == pytest.approx(5.0)

    def test_nonpositive_raises(self) -> None:
        with pytest.raises(ValueError):
            harmonic_mean([1.0, -1.0])

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            harmonic_mean([])


# ---------------------------------------------------------------------------
# winsorise
# ---------------------------------------------------------------------------


class TestWinsorise:
    def test_clips_tails(self) -> None:
        vals = list(range(1, 21))  # 1..20
        result = winsorise(vals, lower=0.05, upper=0.95)
        # Values below Q0.05 are clipped up; values above Q0.95 are clipped down.
        # Q0.05 = 1.95, Q0.95 = 19.05 (linear interpolation on 20 points).
        # result[0]=1 is clipped to 1.95; result[1]=2 is above 1.95, so unchanged.
        assert result[0] < result[1]
        assert result[0] == pytest.approx(1.95, abs=1e-9)
        assert result[-1] > result[-2]
        assert result[-1] == pytest.approx(19.05, abs=1e-9)

    def test_preserves_middle(self) -> None:
        vals = [1.0, 5.0, 10.0]
        result = winsorise(vals, lower=0.0, upper=1.0)
        assert result[1] == pytest.approx(5.0)

    def test_empty_returns_empty(self) -> None:
        assert winsorise([]) == []

    def test_length_preserved(self) -> None:
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert len(winsorise(vals)) == len(vals)


# ---------------------------------------------------------------------------
# trim_mean
# ---------------------------------------------------------------------------


class TestTrimMean:
    def test_symmetric(self) -> None:
        # Symmetric dataset — trim mean ≈ mean
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert trim_mean(vals, proportion=0.2) == pytest.approx(3.0)

    def test_outlier_removed(self) -> None:
        vals = [1.0, 2.0, 3.0, 100.0]
        tm = trim_mean(vals, proportion=0.25)
        assert tm < 50.0  # outlier excluded

    def test_zero_proportion(self) -> None:
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert trim_mean(vals, proportion=0.0) == pytest.approx(3.0)

    def test_invalid_proportion_raises(self) -> None:
        with pytest.raises(ValueError):
            trim_mean([1.0, 2.0], proportion=0.5)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            trim_mean([])


# ---------------------------------------------------------------------------
# entropy
# ---------------------------------------------------------------------------


class TestEntropy:
    def test_uniform_distribution(self) -> None:
        # H(uniform over 4) = log(4) ≈ 1.386 nats
        result = entropy([1, 1, 1, 1])
        assert result == pytest.approx(math.log(4), rel=1e-6)

    def test_deterministic(self) -> None:
        assert entropy([1, 0, 0]) == pytest.approx(0.0)

    def test_all_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            entropy([0, 0, 0])

    def test_negative_count_raises(self) -> None:
        with pytest.raises(ValueError):
            entropy([1, -1, 2])

    def test_unnormalised_counts(self) -> None:
        # [10, 10] should give same entropy as [1, 1]
        assert entropy([10, 10]) == pytest.approx(entropy([1, 1]))
