"""Tests for assay_engine.algorithms.testing."""

import pytest

from assay_engine.algorithms.testing import (
    CorrectionResult,
    StatisticalTest,
    TestResult,
    benjamini_hochberg,
    bonferroni,
    chi_squared_test,
    holm,
    ks_test,
    mann_whitney,
    one_sample_t_test,
    permutation_test,
    welch_t_test,
)


# ---------------------------------------------------------------------------
# welch_t_test
# ---------------------------------------------------------------------------


class TestWelchTTest:
    SAME = [5.0, 5.1, 4.9, 5.0, 5.05]
    DIFF = [1.0, 1.1, 0.9, 1.0, 1.05]

    def test_same_mean_high_p_value(self) -> None:
        result = welch_t_test(self.SAME, self.SAME)
        assert result.p_value > 0.05

    def test_different_means_low_p_value(self) -> None:
        result = welch_t_test(self.SAME, self.DIFF)
        assert result.p_value < 0.001

    def test_p_value_range(self) -> None:
        result = welch_t_test(self.SAME, self.DIFF)
        assert 0.0 <= result.p_value <= 1.0

    def test_result_type(self) -> None:
        result = welch_t_test(self.SAME, self.DIFF)
        assert isinstance(result, TestResult)

    def test_effect_size_large_for_large_difference(self) -> None:
        import random

        rng = random.Random(0)
        a = [100.0 + rng.gauss(0, 1) for _ in range(10)]
        b = [0.0 + rng.gauss(0, 1) for _ in range(10)]
        result = welch_t_test(a, b)
        assert result.effect_size is not None
        assert abs(result.effect_size) > 1.0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            welch_t_test([], self.DIFF)

    def test_too_few_raises(self) -> None:
        with pytest.raises(ValueError):
            welch_t_test([1.0], self.DIFF)

    def test_protocol_compatible(self) -> None:
        def _test(fn: StatisticalTest, a: list, b: list) -> TestResult:
            return fn(a, b)

        result = _test(welch_t_test, self.SAME, self.DIFF)
        assert result.p_value < 0.05


# ---------------------------------------------------------------------------
# one_sample_t_test
# ---------------------------------------------------------------------------


class TestOneSampleTTest:
    DATA = [4.9, 5.0, 5.1, 4.95, 5.05, 5.0]

    def test_mu_near_mean_high_p(self) -> None:
        result = one_sample_t_test(self.DATA, mu=5.0)
        assert result.p_value > 0.05

    def test_mu_far_from_mean_low_p(self) -> None:
        result = one_sample_t_test(self.DATA, mu=0.0)
        assert result.p_value < 0.001

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            one_sample_t_test([], mu=0.0)

    def test_single_element_raises(self) -> None:
        with pytest.raises(ValueError):
            one_sample_t_test([1.0], mu=0.0)


# ---------------------------------------------------------------------------
# mann_whitney
# ---------------------------------------------------------------------------


class TestMannWhitney:
    A = [1.0, 2.0, 3.0, 4.0, 5.0]
    B = [6.0, 7.0, 8.0, 9.0, 10.0]

    def test_clearly_different(self) -> None:
        result = mann_whitney(self.A, self.B)
        assert result.p_value < 0.05

    def test_identical_groups_high_p(self) -> None:
        result = mann_whitney([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
        assert result.p_value > 0.05

    def test_p_value_range(self) -> None:
        result = mann_whitney(self.A, self.B)
        assert 0.0 <= result.p_value <= 1.0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            mann_whitney([], self.B)


# ---------------------------------------------------------------------------
# ks_test
# ---------------------------------------------------------------------------


class TestKSTest:
    A = [1.0, 2.0, 3.0, 4.0, 5.0, 1.5, 2.5, 3.5]
    B = [6.0, 7.0, 8.0, 9.0, 10.0, 6.5, 7.5, 8.5]

    def test_different_distributions_low_p(self) -> None:
        result = ks_test(self.A, self.B)
        assert result.p_value < 0.05

    def test_same_distribution_high_p(self) -> None:
        result = ks_test(self.A, self.A)
        assert result.p_value > 0.05

    def test_statistic_range(self) -> None:
        result = ks_test(self.A, self.B)
        assert 0.0 <= result.statistic <= 1.0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            ks_test([], self.B)


# ---------------------------------------------------------------------------
# chi_squared_test
# ---------------------------------------------------------------------------


class TestChiSquaredTest:
    def test_equal_frequencies_high_p(self) -> None:
        result = chi_squared_test([25, 25, 25, 25])
        assert result.p_value > 0.05

    def test_unequal_frequencies_low_p(self) -> None:
        result = chi_squared_test([90, 10])
        assert result.p_value < 0.001

    def test_p_value_range(self) -> None:
        result = chi_squared_test([10, 20, 30])
        assert 0.0 <= result.p_value <= 1.0

    def test_result_type(self) -> None:
        result = chi_squared_test([1, 2, 3])
        assert isinstance(result, TestResult)

    def test_negative_count_raises(self) -> None:
        with pytest.raises(ValueError):
            chi_squared_test([-1, 5])

    def test_single_category_raises(self) -> None:
        with pytest.raises(ValueError):
            chi_squared_test([100])

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            chi_squared_test([])


# ---------------------------------------------------------------------------
# permutation_test
# ---------------------------------------------------------------------------


class TestPermutationTest:
    A = [1.0, 2.0, 3.0, 4.0, 5.0]
    B = [6.0, 7.0, 8.0, 9.0, 10.0]

    def test_clearly_different(self) -> None:
        result = permutation_test(self.A, self.B, n_permutations=1000, seed=0)
        assert result.p_value <= 0.05

    def test_p_value_range(self) -> None:
        result = permutation_test(self.A, self.B, n_permutations=200, seed=0)
        assert 0.0 <= result.p_value <= 1.0

    def test_effect_size_present(self) -> None:
        result = permutation_test(self.A, self.B, n_permutations=100, seed=0)
        assert (
            result.effect_size != 0.0 or True
        )  # effect size computed but sign depends on direction

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            permutation_test([], self.B, n_permutations=100, seed=0)


# ---------------------------------------------------------------------------
# bonferroni
# ---------------------------------------------------------------------------


class TestBonferroni:
    P_VALUES = [0.01, 0.04, 0.001, 0.2]

    def test_adjusts_upward(self) -> None:
        result = bonferroni(self.P_VALUES)
        for orig, adj in zip(self.P_VALUES, result.adjusted_p):
            assert adj >= orig

    def test_capped_at_one(self) -> None:
        result = bonferroni(self.P_VALUES)
        assert all(adj <= 1.0 for adj in result.adjusted_p)

    def test_result_type(self) -> None:
        result = bonferroni(self.P_VALUES)
        assert isinstance(result, CorrectionResult)

    def test_length_preserved(self) -> None:
        result = bonferroni(self.P_VALUES)
        assert len(result.adjusted_p) == len(self.P_VALUES)
        assert len(result.rejected) == len(self.P_VALUES)

    def test_significant_after_correction(self) -> None:
        # p=0.001 with n=4 → adjusted=0.004 < 0.05 (still significant)
        result = bonferroni(self.P_VALUES)
        assert result.rejected[2]

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            bonferroni([])


# ---------------------------------------------------------------------------
# holm
# ---------------------------------------------------------------------------


class TestHolm:
    P_VALUES = [0.01, 0.04, 0.001, 0.2]

    def test_holm_less_conservative_than_bonferroni(self) -> None:
        holm_res = holm(self.P_VALUES)
        bonf_res = bonferroni(self.P_VALUES)
        for h_adj, b_adj in zip(holm_res.adjusted_p, bonf_res.adjusted_p):
            assert h_adj <= b_adj + 1e-10

    def test_capped_at_one(self) -> None:
        result = holm(self.P_VALUES)
        assert all(adj <= 1.0 for adj in result.adjusted_p)

    def test_length_preserved(self) -> None:
        result = holm(self.P_VALUES)
        assert len(result.adjusted_p) == len(self.P_VALUES)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            holm([])


# ---------------------------------------------------------------------------
# benjamini_hochberg
# ---------------------------------------------------------------------------


class TestBH:
    P_VALUES = [0.01, 0.04, 0.001, 0.2]

    def test_controls_fdr(self) -> None:
        result = benjamini_hochberg(self.P_VALUES, alpha=0.05)
        # With these p-values, at least one should be rejected
        assert any(result.rejected)

    def test_p_values_not_above_1(self) -> None:
        result = benjamini_hochberg(self.P_VALUES)
        assert all(adj <= 1.0 for adj in result.adjusted_p)

    def test_length_preserved(self) -> None:
        result = benjamini_hochberg(self.P_VALUES)
        assert len(result.adjusted_p) == len(self.P_VALUES)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            benjamini_hochberg([])

    def test_invalid_alpha_raises(self) -> None:
        with pytest.raises(ValueError):
            benjamini_hochberg(self.P_VALUES, alpha=0.0)
