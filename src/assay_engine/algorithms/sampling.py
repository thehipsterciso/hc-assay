"""Resampling, splitting, and cross-validation utilities.

All implementations are pure Python; no external dependencies required.

Usage::

    from assay_engine.algorithms.sampling import train_test_split, kfold
    train, test = train_test_split(range(100), test_size=0.2, seed=42)
    for fold_train, fold_val in kfold(range(100), k=5):
        ...
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapResult:
    """Confidence interval from bootstrap resampling.

    Attributes
    ----------
    statistic:  Observed statistic on the original sample.
    mean:       Mean of the bootstrap distribution.
    std:        Standard deviation of bootstrap statistics.
    ci_lower:   Lower bound of the percentile confidence interval.
    ci_upper:   Upper bound of the percentile confidence interval.
    n_resamples: Number of bootstrap resamples drawn.
    """

    statistic: float
    mean: float
    std: float
    ci_lower: float
    ci_upper: float
    n_resamples: int


@dataclass(frozen=True)
class SplitResult(Generic[T]):
    """Train/test (or train/val/test) index split."""

    train: list[T]
    test: list[T]
    val: list[T] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class Splitter(Protocol[T]):
    """A callable that partitions a sequence into train / test subsets."""

    def __call__(self, items: Sequence[T], **kwargs: object) -> SplitResult[T]: ...


# ---------------------------------------------------------------------------
# Train / test split
# ---------------------------------------------------------------------------


def train_test_split(
    items: Sequence[T],
    *,
    test_size: float = 0.2,
    seed: int | None = None,
    shuffle: bool = True,
) -> SplitResult[T]:
    """Randomly split *items* into train and test subsets.

    Parameters
    ----------
    items:     Sequence to split.
    test_size: Fraction of items to place in the test set (default 0.2).
    seed:      Random seed for reproducibility.
    shuffle:   Whether to shuffle before splitting (default True).

    Raises
    ------
    ValueError
        If *test_size* is not in (0, 1) or *items* is empty.
    """
    if not items:
        raise ValueError("items must be non-empty")
    if not 0.0 < test_size < 1.0:
        raise ValueError(f"test_size must be in (0, 1); got {test_size}")

    indices = list(range(len(items)))
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(indices)

    n_test = max(1, math.ceil(len(indices) * test_size))
    test_idx = indices[:n_test]
    train_idx = indices[n_test:]

    return SplitResult(
        train=[items[i] for i in train_idx],
        test=[items[i] for i in test_idx],
    )


def train_val_test_split(
    items: Sequence[T],
    *,
    val_size: float = 0.1,
    test_size: float = 0.1,
    seed: int | None = None,
    shuffle: bool = True,
) -> SplitResult[T]:
    """Three-way split into train, validation, and test sets.

    Parameters
    ----------
    val_size:  Fraction for validation set.
    test_size: Fraction for test set.
    """
    if not items:
        raise ValueError("items must be non-empty")
    if val_size + test_size >= 1.0 or val_size <= 0 or test_size <= 0:
        raise ValueError(f"val_size + test_size must be in (0, 1); got {val_size + test_size}")

    indices = list(range(len(items)))
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(indices)

    n = len(indices)
    n_test = max(1, math.ceil(n * test_size))
    n_val = max(1, math.ceil(n * val_size))

    test_idx = indices[:n_test]
    val_idx = indices[n_test : n_test + n_val]
    train_idx = indices[n_test + n_val :]

    return SplitResult(
        train=[items[i] for i in train_idx],
        val=[items[i] for i in val_idx],
        test=[items[i] for i in test_idx],
    )


# ---------------------------------------------------------------------------
# K-fold cross-validation
# ---------------------------------------------------------------------------


def kfold(
    items: Sequence[T],
    k: int = 5,
    *,
    seed: int | None = None,
    shuffle: bool = True,
) -> list[SplitResult[T]]:
    """K-fold cross-validation splits.

    Returns *k* folds; each fold uses 1/k of data for validation and the
    remaining (k-1)/k for training.  No overlap between validation folds.

    Parameters
    ----------
    k:       Number of folds (default 5).
    shuffle: Shuffle items before folding.
    seed:    Random seed (only used when shuffle=True).

    Raises
    ------
    ValueError
        If k < 2 or k > len(items).
    """
    n = len(items)
    if n == 0:
        raise ValueError("items must be non-empty")
    if k < 2 or k > n:
        raise ValueError(f"k must be in [2, {n}]; got {k}")

    indices = list(range(n))
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(indices)

    fold_size = n // k
    remainder = n % k
    folds: list[list[int]] = []
    start = 0
    for i in range(k):
        end = start + fold_size + (1 if i < remainder else 0)
        folds.append(indices[start:end])
        start = end

    results: list[SplitResult[T]] = []
    for val_fold in folds:
        val_set = set(val_fold)
        train_idx = [i for i in indices if i not in val_set]
        results.append(
            SplitResult(
                train=[items[i] for i in train_idx],
                test=[items[i] for i in val_fold],
            )
        )
    return results


def stratified_kfold(
    items: Sequence[T],
    labels: Sequence[Any],
    k: int = 5,
    *,
    seed: int | None = None,
    shuffle: bool = True,
) -> list[SplitResult[T]]:
    """Stratified K-fold — preserves class proportions in each fold.

    Parameters
    ----------
    items:  Sequence of items to split.
    labels: Class label for each item (must have the same length as *items*).
    k:      Number of folds.

    Raises
    ------
    ValueError
        If lengths differ or k is out of range.
    """
    n = len(items)
    if len(labels) != n:
        raise ValueError(f"items and labels must have the same length; got {n} and {len(labels)}")
    if n == 0:
        raise ValueError("items must be non-empty")
    if k < 2 or k > n:
        raise ValueError(f"k must be in [2, {n}]; got {k}")

    # Group indices by label
    label_indices: dict[Any, list[int]] = defaultdict(list)
    for i, lbl in enumerate(labels):
        label_indices[lbl].append(i)

    rng = random.Random(seed)
    if shuffle:
        for grp in label_indices.values():
            rng.shuffle(grp)

    # Distribute each class's indices round-robin across folds
    folds: list[list[int]] = [[] for _ in range(k)]
    for grp in label_indices.values():
        for j, idx in enumerate(grp):
            folds[j % k].append(idx)

    results: list[SplitResult[T]] = []
    all_indices = list(range(n))
    for fi in range(k):
        val_set = set(folds[fi])
        train_idx = [i for i in all_indices if i not in val_set]
        results.append(
            SplitResult(
                train=[items[i] for i in train_idx],
                test=[items[i] for i in folds[fi]],
            )
        )
    return results


# ---------------------------------------------------------------------------
# Bootstrap resampling
# ---------------------------------------------------------------------------


def bootstrap(
    values: Sequence[float],
    statistic: Any,
    *,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> BootstrapResult:
    """Non-parametric bootstrap confidence interval.

    Resamples *values* with replacement *n_resamples* times, computing
    *statistic* each time to build the sampling distribution.

    Parameters
    ----------
    values:      Original sample.
    statistic:   A callable that accepts a list[float] and returns a float
                 (e.g. ``lambda x: sum(x)/len(x)`` for the mean).
    n_resamples: Number of bootstrap iterations.
    confidence:  Confidence level for the interval (default 0.95).
    seed:        Random seed.

    Returns
    -------
    BootstrapResult with observed statistic, bootstrap mean/std, and CI bounds.
    """
    if not values:
        raise ValueError("values must be non-empty")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1); got {confidence}")

    rng = random.Random(seed)
    n = len(values)
    lst = list(values)
    obs = statistic(lst)

    boot_stats: list[float] = []
    for _ in range(n_resamples):
        resample = [rng.choice(lst) for _ in range(n)]
        boot_stats.append(statistic(resample))

    boot_stats.sort()
    alpha = 1.0 - confidence
    lo_idx = int(math.floor(n_resamples * (alpha / 2)))
    hi_idx = min(int(math.ceil(n_resamples * (1 - alpha / 2))), n_resamples - 1)

    mean = sum(boot_stats) / n_resamples
    var = sum((s - mean) ** 2 for s in boot_stats) / (n_resamples - 1)
    std = math.sqrt(var)

    return BootstrapResult(
        statistic=obs,
        mean=mean,
        std=std,
        ci_lower=boot_stats[lo_idx],
        ci_upper=boot_stats[hi_idx],
        n_resamples=n_resamples,
    )


# ---------------------------------------------------------------------------
# Simple random sampling
# ---------------------------------------------------------------------------


def reservoir_sample(items: Sequence[T], n: int, *, seed: int | None = None) -> list[T]:
    """Vitter's Algorithm R — uniform random sample without replacement.

    Processes *items* in a single pass, making it suitable for streaming.

    Parameters
    ----------
    n:    Sample size (must be ≤ len(items)).
    seed: Random seed.

    Raises
    ------
    ValueError
        If n ≤ 0 or n > len(items).
    """
    total = len(items)
    if n <= 0 or n > total:
        raise ValueError(f"n must be in [1, {total}]; got {n}")

    rng = random.Random(seed)
    reservoir = list(items[:n])
    for i in range(n, total):
        j = rng.randint(0, i)
        if j < n:
            reservoir[j] = items[i]
    return reservoir
