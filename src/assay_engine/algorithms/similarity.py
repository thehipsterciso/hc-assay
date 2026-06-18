"""Similarity and distance measures — pairwise numeric vector comparison.

Each standalone function satisfies either ``SimilarityFn`` or ``DistanceFn``.
All implementations are pure-Python; no external dependencies required.

**Similarity functions** return values in a bounded range (higher = more similar).
**Distance functions** return non-negative values (lower = more similar).

Usage::

    from assay_engine.algorithms.similarity import cosine, euclidean, jaccard
    sim = cosine([1.0, 0.0, 1.0], [1.0, 1.0, 0.0])  # 0.5
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class SimilarityFn(Protocol):
    """A symmetric pairwise similarity measure.

    Accepts two equal-length numeric vectors; returns a scalar (usually in
    [-1, 1] or [0, 1]) where *higher* means more similar.
    """

    def __call__(self, a: Sequence[float], b: Sequence[float]) -> float: ...


@runtime_checkable
class DistanceFn(Protocol):
    """A pairwise distance (metric or pseudo-metric).

    Accepts two equal-length numeric vectors; returns a non-negative scalar
    where *lower* means more similar (0 = identical).
    """

    def __call__(self, a: Sequence[float], b: Sequence[float]) -> float: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate(a: Sequence[float], b: Sequence[float]) -> None:
    if len(a) != len(b):
        raise ValueError(f"vectors must have equal length; got {len(a)} and {len(b)}")
    if not a:
        raise ValueError("vectors must be non-empty")


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


# ---------------------------------------------------------------------------
# Similarity measures  (higher → more similar)
# ---------------------------------------------------------------------------


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in [-1, 1].

    Returns 0.0 when either vector is the zero vector (undefined direction).
    Clamped to [-1, 1] to absorb floating-point rounding past the boundary.

    Industry standard for text/embedding comparison.
    """
    _validate(a, b)
    na = _norm(a)
    nb = _norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(-1.0, min(1.0, _dot(a, b) / (na * nb)))


def pearson(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson product-moment correlation coefficient in [-1, 1].

    Returns 0.0 when either input is constant (zero variance).
    Measures *linear* co-variation; insensitive to scale.
    """
    _validate(a, b)
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da == 0.0 or db == 0.0:
        return 0.0
    return max(-1.0, min(1.0, num / (da * db)))


def jaccard(a: Sequence[float], b: Sequence[float]) -> float:
    """Jaccard index for binary / sparse vectors in [0, 1].

    Treats any non-zero element as present in the set. Returns 1.0 when both
    vectors are all-zero (two empty sets are identical by convention).

    Preferred for high-dimensional sparse features (bag-of-words, one-hot).
    """
    _validate(a, b)
    sa = {i for i, v in enumerate(a) if v != 0.0}
    sb = {i for i, v in enumerate(b) if v != 0.0}
    union = sa | sb
    if not union:
        return 1.0
    return len(sa & sb) / len(union)


def overlap_coefficient(a: Sequence[float], b: Sequence[float]) -> float:
    """Overlap (Szymkiewicz–Simpson) coefficient in [0, 1].

    Like Jaccard but normalises by the *smaller* set — useful when one set
    is a subset of the other (asymmetric membership patterns).
    """
    _validate(a, b)
    sa = {i for i, v in enumerate(a) if v != 0.0}
    sb = {i for i, v in enumerate(b) if v != 0.0}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


# ---------------------------------------------------------------------------
# Distance measures  (lower → more similar)
# ---------------------------------------------------------------------------


def euclidean(a: Sequence[float], b: Sequence[float]) -> float:
    """Euclidean (L2) distance.  Always ≥ 0; 0 iff vectors are identical."""
    _validate(a, b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def manhattan(a: Sequence[float], b: Sequence[float]) -> float:
    """Manhattan (L1 / taxicab) distance.

    More robust to outliers than L2; preferred for high-dimensional sparse data.
    """
    _validate(a, b)
    return sum(abs(x - y) for x, y in zip(a, b))


def chebyshev(a: Sequence[float], b: Sequence[float]) -> float:
    """Chebyshev (L∞) distance — maximum absolute coordinate difference."""
    _validate(a, b)
    return max(abs(x - y) for x, y in zip(a, b))


def minkowski(a: Sequence[float], b: Sequence[float], *, p: float = 2.0) -> float:
    """Minkowski distance of order *p*.

    Generalises L1 (p=1), L2 (p=2), and L∞ (p=∞).
    Requires p ≥ 1 to satisfy the triangle inequality.
    """
    _validate(a, b)
    if p < 1.0:
        raise ValueError(f"p must be ≥ 1 to satisfy triangle inequality; got {p}")
    if math.isinf(p):
        return chebyshev(a, b)
    return float(sum(abs(x - y) ** p for x, y in zip(a, b)) ** (1.0 / p))


def hamming(a: Sequence[float], b: Sequence[float]) -> float:
    """Hamming distance normalised to [0, 1] — fraction of differing positions.

    Designed for binary or categorical vectors of equal length; works for any
    same-length sequences but equality is exact float comparison.
    """
    _validate(a, b)
    return sum(1.0 for x, y in zip(a, b) if x != y) / len(a)


def canberra(a: Sequence[float], b: Sequence[float]) -> float:
    """Canberra distance — weighted L1 normalised by coordinate magnitudes.

    Sensitive to small changes near the origin; useful for data where relative
    differences matter more than absolute differences.
    """
    _validate(a, b)
    total = 0.0
    for x, y in zip(a, b):
        denom = abs(x) + abs(y)
        if denom != 0.0:
            total += abs(x - y) / denom
    return total


# ---------------------------------------------------------------------------
# Matrix utilities
# ---------------------------------------------------------------------------


def similarity_matrix(
    rows: Sequence[Sequence[float]],
    fn: SimilarityFn | None = None,
) -> list[list[float]]:
    """Compute a full n×n pairwise similarity matrix.

    Uses ``cosine`` by default.  The result is symmetric (``M[i][j] == M[j][i]``)
    and the diagonal is 1.0 for cosine (self-similarity).

    Time complexity: O(n² · d) where d is the vector dimension.
    """
    measure: SimilarityFn = fn if fn is not None else cosine
    n = len(rows)
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        mat[i][i] = measure(rows[i], rows[i])
        for j in range(i + 1, n):
            v = measure(rows[i], rows[j])
            mat[i][j] = v
            mat[j][i] = v
    return mat


def distance_matrix(
    rows: Sequence[Sequence[float]],
    fn: DistanceFn | None = None,
) -> list[list[float]]:
    """Compute a full n×n pairwise distance matrix.

    Uses ``euclidean`` by default.  Diagonal is always 0.0.
    """
    measure: DistanceFn = fn if fn is not None else euclidean
    n = len(rows)
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            v = measure(rows[i], rows[j])
            mat[i][j] = v
            mat[j][i] = v
    return mat
