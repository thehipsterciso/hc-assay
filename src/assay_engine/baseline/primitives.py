"""Dependency-light, deterministic numeric primitives — the baseline's raw material.

These are the small, exact, NumPy-free building blocks the methodology calls "raw material"
for a baseline: similarity/distance and descriptive statistics over a
:class:`~assay_engine.contracts.features.FeatureMatrix`. They are deterministic (no RNG, no
iteration-order dependence) and pure, so a study can assemble a simple baseline — and the
engine can unit-test these invariants — with no heavy dependency.

Studies needing performance or richer ML (embedding models, clustering, graph/topology) bring
their own builders implementing :class:`~assay_engine.baseline.toolkit.BaselineBuilder`; the
engine deliberately does not prescribe those choices (ADR-0002). Heavier engine helpers may be
added later under the optional ``baseline`` extra, but the contract here stays dependency-free.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

Vector = Sequence[float]


def _check_same_length(a: Vector, b: Vector) -> None:
    if len(a) != len(b):
        raise ValueError(f"vectors must have equal length; got {len(a)} and {len(b)}")


def _check_finite(*vectors: Vector) -> None:
    """Reject non-finite components. Without this a NaN/inf could flow into cosine and be
    silently clamped to a false 1.0 (audit #B6); consistent with descriptive_stats."""
    for vec in vectors:
        for x in vec:
            if not math.isfinite(x):
                raise ValueError(f"vector components must be finite; got {x}")


def dot(a: Vector, b: Vector) -> float:
    _check_same_length(a, b)
    return math.fsum(x * y for x, y in zip(a, b))


def l2_norm(a: Vector) -> float:
    return math.sqrt(math.fsum(x * x for x in a))


def _clamp_unit(x: float) -> float:
    """Clamp to [-1, 1] to absorb floating-point overshoot (e.g. self-similarity 1.0000…002)."""
    return max(-1.0, min(1.0, x))


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity in [-1, 1]. A zero vector has no direction, so its similarity to
    anything is defined as 0.0 (rather than NaN). The result is clamped to [-1, 1] so float
    rounding cannot push it outside the documented range (audit #B3)."""
    _check_same_length(a, b)
    _check_finite(a, b)
    na, nb = l2_norm(a), l2_norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return _clamp_unit(dot(a, b) / (na * nb))


def euclidean_distance(a: Vector, b: Vector) -> float:
    _check_same_length(a, b)
    _check_finite(a, b)
    return math.sqrt(math.fsum((x - y) ** 2 for x, y in zip(a, b)))


def _cosine_matrix_pure(rows: Sequence[Vector]) -> list[list[float]]:
    """Pure-Python reference implementation — O(n²·d). Correct but slow; the public function
    dispatches to a numpy path at scale when available."""
    n = len(rows)
    _check_finite(*rows)
    norms = [l2_norm(r) for r in rows]
    out = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            if norms[i] == 0.0 or norms[j] == 0.0:
                sim = 0.0
            elif i == j:
                sim = 1.0  # a non-zero vector's self-similarity is exactly 1.0 (no float drift)
            else:
                sim = _clamp_unit(dot(rows[i], rows[j]) / (norms[i] * norms[j]))
            out[i][j] = sim
            out[j][i] = sim
    return out


def _cosine_ndarray(rows: Sequence[Vector]) -> Any:
    """Compute the cosine matrix as a numpy ndarray (no nested-list boxing)."""
    import numpy as np

    x = np.asarray(rows, dtype=float)
    if x.ndim != 2:
        raise ValueError("rows must be a 2-D collection of equal-length vectors")
    if not np.isfinite(x).all():
        raise ValueError("vector components must be finite")
    norms = np.linalg.norm(x, axis=1)
    if not np.isfinite(norms).all():
        # finite inputs can still overflow when squared (||x||) on huge-magnitude vectors;
        # reject rather than silently produce inf/inf similarities (audit N1; restores parity
        # with the pure path, which raises on the same input).
        raise ValueError("vector norm overflow — component magnitudes are too large")
    zero = norms == 0.0
    safe = np.where(zero, 1.0, norms)
    xn = x / safe[:, None]
    m = xn @ xn.T
    np.clip(m, -1.0, 1.0, out=m)
    if zero.any():  # zero vectors have no direction → similarity 0 to everything
        m[zero, :] = 0.0
        m[:, zero] = 0.0
    np.fill_diagonal(m, np.where(zero, 0.0, 1.0))
    return m


def _cosine_matrix_numpy(rows: Sequence[Vector]) -> list[list[float]]:
    return [[float(v) for v in row] for row in _cosine_ndarray(rows)]


def cosine_similarity_matrix_array(rows: Sequence[Vector]) -> Any:
    """The cosine matrix as a numpy ndarray — no nested-list boxing (#106).

    For large corpora the nested-list form of :func:`cosine_similarity_matrix` multiplies peak
    memory several-fold; a builder operating at scale should keep the ndarray and store it in the
    baseline's ``contents``. The determinism freeze still copies the array's bytes once
    (``freeze`` -> ``tobytes()`` into a ``(kind, shape, bytes)`` descriptor, O(size)) — far cheaper
    than freezing a deep nested list element-by-element, but NOT zero-copy/O(1) (pass 4, #G-024).
    Requires numpy (the ``baseline`` extra).
    """
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "cosine_similarity_matrix_array requires numpy (the 'baseline' extra)"
        ) from exc
    if not rows:
        return np.empty((0, 0), dtype=float)
    return _cosine_ndarray(rows)


def cosine_similarity_matrix(rows: Sequence[Vector]) -> list[list[float]]:
    """Full symmetric cosine-similarity matrix (diagonal 1.0 for non-zero vectors, 0.0 for zero).

    Pure-Python is O(n²·d) and does not scale (a corpus of thousands of embeddings would take
    minutes-to-hours); when numpy is available (the optional ``baseline`` extra) this dispatches
    to a vectorized path that is orders of magnitude faster. The two paths agree to within
    floating-point tolerance (both clamp to [-1, 1]); a study needing byte-identical
    reproducibility should pin its environment (the determinism harness records component
    versions for exactly this reason).
    """
    if not rows:
        return []
    try:
        import numpy  # noqa: F401
    except ImportError:
        return _cosine_matrix_pure(rows)
    return _cosine_matrix_numpy(rows)


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation quantile (``q`` in [0, 1]) over already-sorted values."""
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"quantile q must be in [0, 1]; got {q}")
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = q * (n - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def descriptive_stats(values: Sequence[float]) -> dict[str, float]:
    """Descriptive statistics of ``values``.

    Returns ``n`` (count), ``mean``, ``std`` (sample std, ddof=1; ``0.0`` for a single value
    rather than NaN), ``min``, ``max``, and ``q25``/``median``/``q75`` (linear-interpolation
    quantiles). Raises on an empty input or any non-finite value.
    """
    if not values:
        raise ValueError("descriptive_stats requires at least one value")
    n = len(values)
    for v in values:
        if not math.isfinite(v):
            raise ValueError(f"values must be finite; got {v}")
    mean = math.fsum(values) / n
    if n == 1:
        std = 0.0
    else:
        var = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
        std = math.sqrt(var)
    s = sorted(values)
    return {
        "n": float(n),
        "mean": mean,
        "std": std,
        "min": s[0],
        "max": s[-1],
        "q25": _quantile(s, 0.25),
        "median": _quantile(s, 0.5),
        "q75": _quantile(s, 0.75),
    }
