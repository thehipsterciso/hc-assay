"""Tests for assay_engine.algorithms.sampling."""

import pytest

from assay_engine.algorithms.sampling import (
    BootstrapResult,
    SplitResult,
    bootstrap,
    kfold,
    reservoir_sample,
    stratified_kfold,
    train_test_split,
    train_val_test_split,
)


ITEMS = list(range(100))


# ---------------------------------------------------------------------------
# train_test_split
# ---------------------------------------------------------------------------


class TestTrainTestSplit:
    def test_sizes(self) -> None:
        result = train_test_split(ITEMS, test_size=0.2)
        assert len(result.test) == 20
        assert len(result.train) == 80

    def test_no_overlap(self) -> None:
        result = train_test_split(ITEMS, test_size=0.2, seed=0)
        assert set(result.train).isdisjoint(set(result.test))

    def test_all_items_present(self) -> None:
        result = train_test_split(ITEMS, test_size=0.3, seed=0)
        assert sorted(result.train + result.test) == ITEMS

    def test_reproducible(self) -> None:
        r1 = train_test_split(ITEMS, test_size=0.2, seed=42)
        r2 = train_test_split(ITEMS, test_size=0.2, seed=42)
        assert r1.train == r2.train and r1.test == r2.test

    def test_different_seeds_differ(self) -> None:
        r1 = train_test_split(ITEMS, test_size=0.2, seed=1)
        r2 = train_test_split(ITEMS, test_size=0.2, seed=2)
        assert r1.train != r2.train

    def test_no_shuffle(self) -> None:
        result = train_test_split(ITEMS, test_size=0.2, shuffle=False)
        assert result.test == ITEMS[:20]
        assert result.train == ITEMS[20:]

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            train_test_split([], test_size=0.2)

    def test_invalid_test_size_raises(self) -> None:
        with pytest.raises(ValueError):
            train_test_split(ITEMS, test_size=1.0)

    def test_result_type(self) -> None:
        result = train_test_split(ITEMS, test_size=0.1)
        assert isinstance(result, SplitResult)


# ---------------------------------------------------------------------------
# train_val_test_split
# ---------------------------------------------------------------------------


class TestTrainValTestSplit:
    def test_three_way_sizes(self) -> None:
        result = train_val_test_split(ITEMS, val_size=0.1, test_size=0.1, seed=0)
        assert len(result.test) == 10
        assert len(result.val) == 10
        assert len(result.train) == 80

    def test_no_overlap(self) -> None:
        result = train_val_test_split(ITEMS, val_size=0.1, test_size=0.1, seed=0)
        all_sets = [set(result.train), set(result.val), set(result.test)]
        for i in range(3):
            for j in range(i + 1, 3):
                assert all_sets[i].isdisjoint(all_sets[j])

    def test_all_items_covered(self) -> None:
        result = train_val_test_split(ITEMS, val_size=0.2, test_size=0.1, seed=0)
        combined = sorted(result.train + result.val + result.test)
        assert combined == ITEMS

    def test_invalid_fractions_raise(self) -> None:
        with pytest.raises(ValueError):
            train_val_test_split(ITEMS, val_size=0.5, test_size=0.5)


# ---------------------------------------------------------------------------
# kfold
# ---------------------------------------------------------------------------


class TestKFold:
    def test_n_folds(self) -> None:
        folds = kfold(ITEMS, k=5)
        assert len(folds) == 5

    def test_each_fold_val_size(self) -> None:
        folds = kfold(ITEMS, k=5)
        val_sizes = [len(f.test) for f in folds]
        assert all(s == 20 for s in val_sizes)

    def test_val_folds_non_overlapping(self) -> None:
        folds = kfold(ITEMS, k=5, seed=0)
        val_sets = [set(f.test) for f in folds]
        all_vals: set[int] = set()
        for vs in val_sets:
            assert all_vals.isdisjoint(vs), "validation folds must not overlap"
            all_vals |= vs
        assert all_vals == set(ITEMS)

    def test_each_fold_covers_all_train_val(self) -> None:
        folds = kfold(ITEMS, k=4, seed=0)
        for fold in folds:
            assert sorted(fold.train + fold.test) == ITEMS

    def test_k_too_large_raises(self) -> None:
        with pytest.raises(ValueError):
            kfold([1, 2], k=3)

    def test_k_one_raises(self) -> None:
        with pytest.raises(ValueError):
            kfold(ITEMS, k=1)


# ---------------------------------------------------------------------------
# stratified_kfold
# ---------------------------------------------------------------------------


class TestStratifiedKFold:
    LABELS = [0] * 50 + [1] * 50

    def test_n_folds(self) -> None:
        folds = stratified_kfold(ITEMS, self.LABELS, k=5)
        assert len(folds) == 5

    def test_label_balance(self) -> None:
        folds = stratified_kfold(ITEMS, self.LABELS, k=5, seed=0)
        for fold in folds:
            val_labels = [self.LABELS[i] for i in range(len(ITEMS)) if ITEMS[i] in fold.test]
            n0 = sum(1 for lbl in val_labels if lbl == 0)
            n1 = sum(1 for lbl in val_labels if lbl == 1)
            assert abs(n0 - n1) <= 2, "classes should be balanced in each fold"

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError):
            stratified_kfold(ITEMS, self.LABELS[:10], k=5)

    def test_all_items_covered_per_fold(self) -> None:
        folds = stratified_kfold(ITEMS, self.LABELS, k=5, seed=0)
        for fold in folds:
            assert sorted(fold.train + fold.test) == ITEMS


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


class TestBootstrap:
    VALUES = [float(i) for i in range(1, 101)]

    def test_result_type(self) -> None:
        result = bootstrap(self.VALUES, lambda x: sum(x) / len(x), seed=0)
        assert isinstance(result, BootstrapResult)

    def test_observed_statistic(self) -> None:
        result = bootstrap(self.VALUES, lambda x: sum(x) / len(x), seed=0)
        assert result.statistic == pytest.approx(50.5)

    def test_ci_contains_true_mean(self) -> None:
        result = bootstrap(self.VALUES, lambda x: sum(x) / len(x), n_resamples=5000, seed=0)
        assert result.ci_lower <= 50.5 <= result.ci_upper

    def test_ci_tighter_with_more_resamples(self) -> None:
        r1 = bootstrap(self.VALUES, lambda x: sum(x) / len(x), n_resamples=100, seed=0)
        r2 = bootstrap(self.VALUES, lambda x: sum(x) / len(x), n_resamples=5000, seed=0)
        width1 = r1.ci_upper - r1.ci_lower
        width2 = r2.ci_upper - r2.ci_lower
        # More resamples → more stable interval; this is a probabilistic check
        # but with these seeds it reliably holds
        assert width2 <= width1 * 1.5

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            bootstrap([], lambda x: 0.0)

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(ValueError):
            bootstrap(self.VALUES, lambda x: 0.0, confidence=1.1)


# ---------------------------------------------------------------------------
# reservoir_sample
# ---------------------------------------------------------------------------


class TestReservoirSample:
    def test_size(self) -> None:
        sample = reservoir_sample(ITEMS, 10, seed=0)
        assert len(sample) == 10

    def test_subset(self) -> None:
        sample = reservoir_sample(ITEMS, 10, seed=0)
        assert set(sample) <= set(ITEMS)

    def test_no_duplicates(self) -> None:
        sample = reservoir_sample(ITEMS, 50, seed=0)
        assert len(set(sample)) == 50

    def test_reproducible(self) -> None:
        s1 = reservoir_sample(ITEMS, 10, seed=7)
        s2 = reservoir_sample(ITEMS, 10, seed=7)
        assert s1 == s2

    def test_n_equals_total(self) -> None:
        sample = reservoir_sample(ITEMS, len(ITEMS), seed=0)
        assert sorted(sample) == ITEMS

    def test_n_too_large_raises(self) -> None:
        with pytest.raises(ValueError):
            reservoir_sample(ITEMS, len(ITEMS) + 1)

    def test_n_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            reservoir_sample(ITEMS, 0)
