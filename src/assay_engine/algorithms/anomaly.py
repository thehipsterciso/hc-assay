"""Anomaly and outlier detection algorithms.

Each detector implements the ``AnomalyDetector`` Protocol.
All implementations are pure Python; no external dependencies required.

Usage::

    from assay_engine.algorithms.anomaly import zscore_detector, lof
    result = zscore_detector([1.0, 2.0, 100.0, 2.5, 1.5], threshold=3.0)
    print(result.outlier_flags)  # [False, False, True, False, False]
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnomalyResult:
    """Output of an anomaly/outlier detection pass.

    Attributes
    ----------
    scores:        Per-point anomaly score (higher = more anomalous).
    outlier_flags: Boolean flag per point (True = outlier).
    threshold:     Score threshold used to set flags.
    n_outliers:    Count of points flagged as outliers.
    """

    scores: list[float]
    outlier_flags: list[bool]
    threshold: float
    n_outliers: int


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class AnomalyDetector(Protocol):
    """A callable that scores a sequence of values for anomalousness."""

    def __call__(self, values: Sequence[float], *, threshold: float = 3.0) -> AnomalyResult: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _std(values: Sequence[float], ddof: int = 1) -> float:
    n = len(values)
    if n <= ddof:
        return 0.0
    mu = _mean(values)
    return math.sqrt(sum((x - mu) ** 2 for x in values) / (n - ddof))


def _median(values: Sequence[float]) -> float:
    sv = sorted(values)
    n = len(sv)
    mid = n // 2
    return sv[mid] if n % 2 else (sv[mid - 1] + sv[mid]) / 2.0


def _mad(values: Sequence[float]) -> float:
    med = _median(values)
    return _median([abs(x - med) for x in values])


# ---------------------------------------------------------------------------
# Z-score detector
# ---------------------------------------------------------------------------


def zscore_detector(
    values: Sequence[float],
    *,
    threshold: float = 3.0,
) -> AnomalyResult:
    """Flag outliers where |z-score| > threshold (default 3σ).

    Uses sample standard deviation (ddof=1).  Returns all-False flags
    and zero scores when std = 0 (constant input).

    Parameters
    ----------
    threshold: Number of standard deviations beyond which a point is an outlier.
    """
    if not values:
        raise ValueError("values must be non-empty")

    mu = _mean(values)
    s = _std(values, ddof=1)

    if s == 0.0:
        scores = [0.0] * len(values)
        flags = [False] * len(values)
    else:
        scores = [abs(x - mu) / s for x in values]
        flags = [sc > threshold for sc in scores]

    return AnomalyResult(
        scores=scores,
        outlier_flags=flags,
        threshold=threshold,
        n_outliers=sum(flags),
    )


# ---------------------------------------------------------------------------
# IQR / Tukey fence detector
# ---------------------------------------------------------------------------


def iqr_detector(
    values: Sequence[float],
    *,
    threshold: float = 1.5,
) -> AnomalyResult:
    """Tukey fence outlier detection using the interquartile range.

    Points outside [Q1 − k·IQR, Q3 + k·IQR] are flagged, where k = *threshold*
    (default 1.5 for "outlier", 3.0 for "far outlier").

    The anomaly score is how many IQR-widths the point exceeds the fence
    (0.0 for points inside the fence).
    """
    if not values:
        raise ValueError("values must be non-empty")

    sv = sorted(values)
    n = len(sv)

    def _q(p: float) -> float:
        idx = p * (n - 1)
        lo = int(idx)
        hi = lo + 1
        if hi >= n:
            return sv[-1]
        return sv[lo] + (idx - lo) * (sv[hi] - sv[lo])

    q1 = _q(0.25)
    q3 = _q(0.75)
    iqr = q3 - q1

    lower = q1 - threshold * iqr
    upper = q3 + threshold * iqr

    scores: list[float] = []
    flags: list[bool] = []
    for x in values:
        if iqr == 0.0:
            scores.append(0.0)
            flags.append(False)
        elif x < lower:
            sc = (lower - x) / iqr
            scores.append(sc)
            flags.append(True)
        elif x > upper:
            sc = (x - upper) / iqr
            scores.append(sc)
            flags.append(True)
        else:
            scores.append(0.0)
            flags.append(False)

    return AnomalyResult(
        scores=scores,
        outlier_flags=flags,
        threshold=threshold,
        n_outliers=sum(flags),
    )


# ---------------------------------------------------------------------------
# MAD-based robust detector
# ---------------------------------------------------------------------------


def mad_detector(
    values: Sequence[float],
    *,
    threshold: float = 3.5,
) -> AnomalyResult:
    """Median Absolute Deviation (MAD) robust outlier detector.

    Robust z-score: 0.6745 · (x − median) / MAD.
    Threshold of 3.5 follows Iglewicz & Hoaglin (1993) recommendation.

    More robust than z-score when outliers contaminate the sample, since
    the median and MAD are resistant to extreme values.
    """
    if not values:
        raise ValueError("values must be non-empty")

    med = _median(values)
    m = _mad(values)

    if m == 0.0:
        scores = [0.0] * len(values)
        flags = [False] * len(values)
    else:
        scores = [abs(0.6745 * (x - med) / m) for x in values]
        flags = [sc > threshold for sc in scores]

    return AnomalyResult(
        scores=scores,
        outlier_flags=flags,
        threshold=threshold,
        n_outliers=sum(flags),
    )


# ---------------------------------------------------------------------------
# Local Outlier Factor (LOF)
# ---------------------------------------------------------------------------


def _k_nearest(
    points: list[list[float]],
    idx: int,
    k: int,
) -> list[int]:
    """Return indices of the k nearest neighbours of points[idx] (excluding self)."""
    dists = [
        (math.sqrt(sum((a - b) ** 2 for a, b in zip(points[idx], points[j]))), j)
        for j in range(len(points))
        if j != idx
    ]
    dists.sort()
    return [j for _, j in dists[:k]]


def _reach_dist(
    points: list[list[float]],
    i: int,
    j: int,
    k_neighbours: list[list[int]],
) -> float:
    """Reachability distance: max(k-dist(j), d(i, j))."""
    k_dist_j = math.sqrt(sum((a - b) ** 2 for a, b in zip(points[j], points[k_neighbours[j][-1]])))
    d_ij = math.sqrt(sum((a - b) ** 2 for a, b in zip(points[i], points[j])))
    return max(k_dist_j, d_ij)


def lof(
    points: Sequence[Sequence[float]],
    *,
    k: int = 20,
    threshold: float = 1.5,
) -> AnomalyResult:
    """Local Outlier Factor — density-based multivariate anomaly detection.

    Computes the LOF score for each point relative to its k nearest neighbours.
    LOF ≈ 1 indicates the point is in a cluster of similar density.
    LOF >> 1 indicates the point is in a significantly sparser region (outlier).

    Parameters
    ----------
    k:         Number of neighbours for the local density estimate (default 20).
    threshold: LOF score above which a point is flagged as an outlier.

    Time complexity: O(n²·d) with the naive distance computation used here.

    Raises
    ------
    ValueError
        If *points* is empty or k ≥ len(points).
    """
    pts = [list(p) for p in points]
    n = len(pts)
    if n == 0:
        raise ValueError("points must be non-empty")
    if k >= n:
        raise ValueError(f"k must be < len(points) ({n}); got {k}")

    # k-nearest neighbours for each point
    knn = [_k_nearest(pts, i, k) for i in range(n)]

    # Local reachability density
    lrd: list[float] = []
    for i in range(n):
        avg_rd = sum(_reach_dist(pts, i, j, knn) for j in knn[i]) / k
        lrd.append(1.0 / avg_rd if avg_rd > 0.0 else math.inf)

    # LOF score
    scores: list[float] = []
    for i in range(n):
        avg_lrd_neighbours = sum(lrd[j] for j in knn[i]) / k
        if lrd[i] == 0.0:
            scores.append(0.0)
        elif math.isinf(lrd[i]):
            scores.append(1.0 if avg_lrd_neighbours == math.inf else 0.0)
        else:
            scores.append(avg_lrd_neighbours / lrd[i])

    flags = [sc > threshold for sc in scores]

    return AnomalyResult(
        scores=scores,
        outlier_flags=flags,
        threshold=threshold,
        n_outliers=sum(flags),
    )


# ---------------------------------------------------------------------------
# Isolation scoring (approximate)
# ---------------------------------------------------------------------------


def isolation_score(
    values: Sequence[float],
    *,
    n_trees: int = 100,
    subsample_size: int = 256,
    threshold: float = 0.6,
    seed: int = 0,
) -> AnomalyResult:
    """Simplified 1-D isolation forest for univariate anomaly detection.

    Estimates anomaly score from the average depth at which a value is
    isolated in random partition trees.  Score in (0, 1); values closer
    to 1 are more anomalous.

    This is a univariate approximation; for multivariate data use LOF.

    Parameters
    ----------
    n_trees:        Number of random isolation trees.
    subsample_size: Subsample size per tree (capped at len(values)).
    threshold:      Score above which a point is flagged as an outlier.
    seed:           Random seed for reproducibility.
    """
    import random

    if not values:
        raise ValueError("values must be non-empty")

    n = len(values)
    sub = min(subsample_size, n)
    rng = random.Random(seed)

    def _path_length(x: float, sample: list[float], current_depth: int, limit: int) -> float:
        if len(sample) <= 1 or current_depth >= limit:
            # Correction term from Liu et al. (2008)
            if len(sample) <= 1:
                return current_depth
            m = len(sample)
            correction = 2.0 * (math.log(m - 1) + 0.5772) - 2.0 * (m - 1) / m
            return current_depth + correction
        lo, hi = min(sample), max(sample)
        if lo == hi:
            return current_depth
        split = rng.uniform(lo, hi)
        left = [v for v in sample if v < split]
        right = [v for v in sample if v >= split]
        if x < split:
            return _path_length(x, left, current_depth + 1, limit)
        return _path_length(x, right, current_depth + 1, limit)

    limit = math.ceil(math.log2(sub)) if sub > 1 else 1
    avg_n = 2.0 * (math.log(sub - 1) + 0.5772) - 2.0 * (sub - 1) / sub if sub > 1 else 1.0

    all_depths: list[list[float]] = [[] for _ in range(n)]
    lst = list(values)
    for _ in range(n_trees):
        sample = rng.sample(lst, sub)
        for i, x in enumerate(lst):
            all_depths[i].append(_path_length(x, sample, 0, limit))

    scores: list[float] = []
    for depths in all_depths:
        avg_depth = sum(depths) / len(depths)
        score = 2.0 ** (-avg_depth / avg_n) if avg_n > 0.0 else 0.5
        scores.append(score)

    flags = [sc > threshold for sc in scores]

    return AnomalyResult(
        scores=scores,
        outlier_flags=flags,
        threshold=threshold,
        n_outliers=sum(flags),
    )
