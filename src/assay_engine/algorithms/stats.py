"""Descriptive statistics and distributional summaries.

``SummaryStats`` is the canonical result type; ``describe()`` is the primary
entry point.  Auxiliary functions (z-scores, quantiles, robust scale) are also
provided as standalone callables.

All implementations are pure Python; no external dependencies required.

Usage::

    from assay_engine.algorithms.stats import describe, z_scores
    s = describe([1.0, 2.0, 3.0, 4.0, 5.0])
    s.mean      # 3.0
    s.std       # 1.5811…
    s.skewness  # 0.0  (symmetric)
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SummaryStats:
    """Full descriptive summary of a numeric sample.

    Attributes
    ----------
    n:         Sample count.
    mean:      Arithmetic mean.
    variance:  Sample variance (ddof=1); 0.0 when n=1.
    std:       Sample standard deviation (sqrt of variance).
    minimum:   Minimum value.
    q25:       First quartile (25th percentile, linear interpolation).
    median:    Median (50th percentile).
    q75:       Third quartile (75th percentile).
    maximum:   Maximum value.
    iqr:       Interquartile range (q75 − q25).
    skewness:  Fisher's adjusted skewness; 0 for symmetric distributions.
    kurtosis:  Excess kurtosis (Fisher); 0 for normal, >0 heavy-tailed.
    mad:       Median absolute deviation — robust spread measure.
    """

    n: int
    mean: float
    variance: float
    std: float
    minimum: float
    q25: float
    median: float
    q75: float
    maximum: float
    iqr: float
    skewness: float
    kurtosis: float
    mad: float


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class Summarizer(Protocol):
    """A callable that reduces a numeric sequence to a ``SummaryStats``."""

    def __call__(self, values: Sequence[float]) -> SummaryStats: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _quantile(sv: list[float], p: float) -> float:
    """Linear-interpolation quantile on an already-sorted list."""
    n = len(sv)
    if n == 0:
        raise ValueError("empty sequence")
    if n == 1:
        return sv[0]
    idx = p * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sv[-1]
    frac = idx - lo
    return sv[lo] + frac * (sv[hi] - sv[lo])


# ---------------------------------------------------------------------------
# Primary entry point
# ---------------------------------------------------------------------------


def describe(values: Sequence[float]) -> SummaryStats:
    """Compute the full descriptive summary of *values*.

    Skewness uses Fisher's sample-adjusted formula (G1); kurtosis uses Fisher's
    excess-kurtosis with bias correction suitable for small samples.
    Both return 0.0 when there are insufficient observations or zero variance.

    Raises
    ------
    ValueError
        If *values* is empty.
    """
    if not values:
        raise ValueError("cannot summarise an empty sequence")

    n = len(values)
    sv = sorted(values)
    mean = sum(values) / n

    # sample variance (ddof=1)
    var = sum((x - mean) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(var)

    q25 = _quantile(sv, 0.25)
    median = _quantile(sv, 0.50)
    q75 = _quantile(sv, 0.75)
    iqr = q75 - q25

    # Fisher's G1 adjusted skewness (bias-corrected for samples)
    if std == 0.0 or n < 3:
        skewness = 0.0
    else:
        m3 = sum((x - mean) ** 3 for x in values) / n
        skewness = (m3 / std**3) * math.sqrt(n * (n - 1)) / (n - 2)

    # Excess kurtosis with bias correction (Fisher's G2 variant for samples)
    if std == 0.0 or n < 4:
        kurtosis = 0.0
    else:
        m4 = sum((x - mean) ** 4 for x in values) / n
        raw = m4 / std**4 - 3.0
        kurtosis = ((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * raw + 6.0)

    # Median absolute deviation
    mad = _quantile(sorted(abs(x - median) for x in values), 0.50)

    return SummaryStats(
        n=n,
        mean=mean,
        variance=var,
        std=std,
        minimum=sv[0],
        q25=q25,
        median=median,
        q75=q75,
        maximum=sv[-1],
        iqr=iqr,
        skewness=skewness,
        kurtosis=kurtosis,
        mad=mad,
    )


# ---------------------------------------------------------------------------
# Standalone statistical functions
# ---------------------------------------------------------------------------


def quantile(values: Sequence[float], p: float) -> float:
    """Linear-interpolation quantile at probability *p* ∈ [0, 1]."""
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must be in [0, 1]; got {p}")
    if not values:
        raise ValueError("empty sequence")
    return _quantile(sorted(values), p)


def z_scores(values: Sequence[float]) -> list[float]:
    """Standard z-scores: (x − mean) / std.

    Returns a list of zeros when std = 0 (constant input).
    Uses sample std (ddof=1) for unbiased scale estimation.
    """
    if not values:
        return []
    n = len(values)
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(var)
    if std == 0.0:
        return [0.0] * n
    return [(x - mean) / std for x in values]


def robust_z_scores(values: Sequence[float]) -> list[float]:
    """MAD-based robust z-scores: 0.6745 × (x − median) / MAD.

    The constant 0.6745 (≈ Φ⁻¹(0.75)) makes the scale consistent with the
    normal-distribution σ for Gaussian data. Returns zeros when MAD = 0.

    Preferred over standard z-scores when the sample may contain outliers.
    """
    if not values:
        return []
    n = len(values)
    sv = sorted(values)
    median = _quantile(sv, 0.50)
    mad = _quantile(sorted(abs(x - median) for x in values), 0.50)
    if mad == 0.0:
        return [0.0] * n
    return [0.6745 * (x - median) / mad for x in values]


def geometric_mean(values: Sequence[float]) -> float:
    """Geometric mean of strictly positive values.

    Computed via log-sum-exp for numerical stability.

    Raises
    ------
    ValueError
        If *values* is empty or contains non-positive elements.
    """
    if not values:
        raise ValueError("empty sequence")
    if any(v <= 0 for v in values):
        raise ValueError("geometric mean requires strictly positive values")
    return math.exp(sum(math.log(v) for v in values) / len(values))


def harmonic_mean(values: Sequence[float]) -> float:
    """Harmonic mean of strictly positive values.

    Appropriate for rates and ratios; less sensitive to large outliers
    than the arithmetic mean.

    Raises
    ------
    ValueError
        If *values* is empty or contains non-positive elements.
    """
    if not values:
        raise ValueError("empty sequence")
    if any(v <= 0 for v in values):
        raise ValueError("harmonic mean requires strictly positive values")
    return len(values) / sum(1.0 / v for v in values)


def winsorise(
    values: Sequence[float],
    *,
    lower: float = 0.05,
    upper: float = 0.95,
) -> list[float]:
    """Winsorise *values* by clamping tails at the given quantile bounds.

    Values below the *lower* quantile are set to the *lower* quantile value;
    values above *upper* are set to the *upper* quantile value.
    Reduces the influence of extreme outliers without removing data points.
    """
    if not values:
        return []
    sv = sorted(values)
    lo = _quantile(sv, lower)
    hi = _quantile(sv, upper)
    return [max(lo, min(hi, x)) for x in values]


def trim_mean(values: Sequence[float], *, proportion: float = 0.1) -> float:
    """Trimmed mean — arithmetic mean after removing tail fractions.

    *proportion* is the fraction to remove from *each* tail (default 10%).
    Returns the plain arithmetic mean when proportion = 0.

    Raises
    ------
    ValueError
        If *values* is empty or proportion is outside [0, 0.5).
    """
    if not values:
        raise ValueError("empty sequence")
    if not 0.0 <= proportion < 0.5:
        raise ValueError(f"proportion must be in [0, 0.5); got {proportion}")
    sv = sorted(values)
    n = len(sv)
    k = int(math.floor(n * proportion))
    trimmed = sv[k : n - k] if k > 0 else sv
    if not trimmed:
        raise ValueError("too many values trimmed; reduce proportion")
    return sum(trimmed) / len(trimmed)


def entropy(counts: Sequence[int | float]) -> float:
    """Shannon entropy in nats of a discrete probability distribution.

    *counts* need not be normalised — they are normalised internally.
    Returns 0.0 for a deterministic distribution (single non-zero count).

    Raises
    ------
    ValueError
        If all counts are zero or any count is negative.
    """
    total = sum(counts)
    if total <= 0:
        raise ValueError("counts must sum to a positive number")
    if any(c < 0 for c in counts):
        raise ValueError("counts must be non-negative")
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log(p)
    return h
