"""Clustering algorithms — unsupervised grouping of numeric vectors.

Each algorithm exposes a ``Clusterer`` Protocol for structural typing.
All implementations are pure Python; no external dependencies required.

Usage::

    from assay_engine.algorithms.clustering import kmeans, dbscan, silhouette_score
    labels = kmeans([[1.0, 2.0], [1.1, 2.1], [9.0, 9.0]], k=2).labels
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
class ClusterResult:
    """Output of a clustering algorithm.

    Attributes
    ----------
    labels:    Cluster assignment per input point (-1 = noise, for DBSCAN).
    centroids: Centroid of each cluster (empty for hierarchical/DBSCAN).
    n_clusters: Number of clusters found (excluding noise label -1).
    inertia:   Sum of squared distances to assigned centroid; 0.0 if N/A.
    """

    labels: list[int]
    centroids: list[list[float]]
    n_clusters: int
    inertia: float


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class Clusterer(Protocol):
    """A callable that groups a set of numeric vectors into clusters."""

    def __call__(self, points: Sequence[Sequence[float]], **kwargs: object) -> ClusterResult: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dist_sq(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(_dist_sq(a, b))


def _centroid(cluster: list[list[float]]) -> list[float]:
    d = len(cluster[0])
    return [sum(p[i] for p in cluster) / len(cluster) for i in range(d)]


def _inertia(points: list[list[float]], labels: list[int], centroids: list[list[float]]) -> float:
    total = 0.0
    for p, lbl in zip(points, labels):
        if lbl >= 0:
            total += _dist_sq(p, centroids[lbl])
    return total


# ---------------------------------------------------------------------------
# K-means (k-means++ initialisation)
# ---------------------------------------------------------------------------


def _kmeanspp_init(points: list[list[float]], k: int, rng_seed: int) -> list[list[float]]:
    """K-means++ centroid seeding — O(n·k·d), deterministic given seed."""
    import random

    rng = random.Random(rng_seed)
    centroids: list[list[float]] = [list(rng.choice(points))]
    while len(centroids) < k:
        dists = [min(_dist_sq(p, c) for c in centroids) for p in points]
        total = sum(dists)
        if total == 0.0:
            centroids.append(list(rng.choice(points)))
            continue
        r = rng.random() * total
        cumulative = 0.0
        chosen = points[-1]
        for p, d in zip(points, dists):
            cumulative += d
            if cumulative >= r:
                chosen = p
                break
        centroids.append(list(chosen))
    return centroids


def kmeans(
    points: Sequence[Sequence[float]],
    k: int,
    *,
    max_iter: int = 300,
    tol: float = 1e-4,
    n_init: int = 10,
    seed: int = 0,
) -> ClusterResult:
    """K-means clustering with k-means++ initialisation.

    Runs *n_init* restarts and returns the result with the lowest inertia.
    Convergence is declared when centroid shift < *tol* (L2 norm).

    Parameters
    ----------
    points:   N×d array of numeric vectors.
    k:        Number of clusters (must be ≤ N).
    max_iter: Maximum EM iterations per restart.
    tol:      Convergence threshold on centroid movement.
    n_init:   Number of independent restarts.
    seed:     Random seed base (incremented per restart for diversity).

    Raises
    ------
    ValueError
        If k ≤ 0, k > len(points), or points is empty.
    """
    pts = [list(p) for p in points]
    n = len(pts)
    if n == 0:
        raise ValueError("points must be non-empty")
    if k <= 0 or k > n:
        raise ValueError(f"k must be in [1, {n}]; got {k}")

    best_labels: list[int] = []
    best_centroids: list[list[float]] = []
    best_inertia = math.inf

    for run in range(n_init):
        centroids = _kmeanspp_init(pts, k, seed + run)
        labels = [0] * n

        for _ in range(max_iter):
            # Assignment step
            new_labels = [
                min(range(k), key=lambda ci, p=pt: _dist_sq(p, centroids[ci]))  # type: ignore[misc]
                for pt in pts
            ]

            # Update step
            new_centroids: list[list[float]] = []
            for ci in range(k):
                cluster = [pts[i] for i in range(n) if new_labels[i] == ci]
                if cluster:
                    new_centroids.append(_centroid(cluster))
                else:
                    new_centroids.append(centroids[ci])  # keep old centroid

            shift = sum(_dist(centroids[ci], new_centroids[ci]) for ci in range(k))
            labels = new_labels
            centroids = new_centroids
            if shift < tol:
                break

        inertia = _inertia(pts, labels, centroids)
        if inertia < best_inertia:
            best_inertia = inertia
            best_labels = labels
            best_centroids = centroids

    return ClusterResult(
        labels=best_labels,
        centroids=best_centroids,
        n_clusters=k,
        inertia=best_inertia,
    )


# ---------------------------------------------------------------------------
# Hierarchical agglomerative clustering (complete, single, average linkage)
# ---------------------------------------------------------------------------


def agglomerative(
    points: Sequence[Sequence[float]],
    n_clusters: int,
    *,
    linkage: str = "average",
) -> ClusterResult:
    """Bottom-up agglomerative clustering.

    Merges the closest pair of clusters at each step until *n_clusters*
    remain. Three linkage strategies are supported:

    - ``"single"``   — nearest neighbour (minimum pairwise distance)
    - ``"complete"`` — furthest neighbour (maximum pairwise distance)
    - ``"average"``  — average pairwise distance (UPGMA)

    Complexity: O(n³) — suitable for small datasets (≤ ~500 points).

    Raises
    ------
    ValueError
        If *linkage* is unknown or *n_clusters* is out of range.
    """
    pts = [list(p) for p in points]
    n = len(pts)
    if n == 0:
        raise ValueError("points must be non-empty")
    if not 1 <= n_clusters <= n:
        raise ValueError(f"n_clusters must be in [1, {n}]; got {n_clusters}")
    if linkage not in {"single", "complete", "average"}:
        raise ValueError(f"linkage must be 'single', 'complete', or 'average'; got {linkage!r}")

    # Each cluster is a list of point indices
    clusters: list[list[int]] = [[i] for i in range(n)]

    while len(clusters) > n_clusters:
        best_dist = math.inf
        merge_a = merge_b = -1

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                pairwise = [_dist(pts[a], pts[b]) for a in clusters[i] for b in clusters[j]]
                if linkage == "single":
                    d = min(pairwise)
                elif linkage == "complete":
                    d = max(pairwise)
                else:
                    d = sum(pairwise) / len(pairwise)

                if d < best_dist:
                    best_dist = d
                    merge_a, merge_b = i, j

        merged = clusters[merge_a] + clusters[merge_b]
        clusters = [c for idx, c in enumerate(clusters) if idx not in {merge_a, merge_b}]
        clusters.append(merged)

    labels = [0] * n
    for ci, cluster in enumerate(clusters):
        for idx in cluster:
            labels[idx] = ci

    centroids = [_centroid([pts[i] for i in cluster]) for cluster in clusters]

    return ClusterResult(
        labels=labels,
        centroids=centroids,
        n_clusters=n_clusters,
        inertia=_inertia(pts, labels, centroids),
    )


# ---------------------------------------------------------------------------
# DBSCAN
# ---------------------------------------------------------------------------


def dbscan(
    points: Sequence[Sequence[float]],
    *,
    eps: float = 0.5,
    min_samples: int = 5,
) -> ClusterResult:
    """Density-Based Spatial Clustering of Applications with Noise.

    Assigns labels ≥ 0 to core/border points and -1 to noise.
    Does not require specifying the number of clusters in advance.

    Parameters
    ----------
    eps:         Neighbourhood radius.
    min_samples: Minimum points (including self) to form a core point.

    Time complexity: O(n²) with the naive neighbour search used here.
    """
    pts = [list(p) for p in points]
    n = len(pts)
    if n == 0:
        raise ValueError("points must be non-empty")
    if eps <= 0:
        raise ValueError(f"eps must be positive; got {eps}")
    if min_samples < 1:
        raise ValueError(f"min_samples must be ≥ 1; got {min_samples}")

    neighbours: list[list[int]] = []
    for i in range(n):
        nb = [j for j in range(n) if _dist(pts[i], pts[j]) <= eps]
        neighbours.append(nb)

    labels = [-1] * n
    cluster_id = 0

    for i in range(n):
        if labels[i] != -1:
            continue
        if len(neighbours[i]) < min_samples:
            continue  # noise (for now)

        # Expand cluster
        labels[i] = cluster_id
        queue: list[int] = list(neighbours[i])
        while queue:
            q: int = queue.pop()
            if labels[q] == -1:
                labels[q] = cluster_id
            if labels[q] != cluster_id:
                continue
            labels[q] = cluster_id
            if len(neighbours[q]) >= min_samples:
                for nidx in neighbours[q]:
                    if labels[nidx] == -1:
                        queue.append(nidx)

        cluster_id += 1

    found = cluster_id
    # Compute centroids for non-noise clusters
    centroids: list[list[float]] = []
    for ci in range(found):
        cluster_pts = [pts[i] for i in range(n) if labels[i] == ci]
        centroids.append(_centroid(cluster_pts) if cluster_pts else [])

    return ClusterResult(
        labels=labels,
        centroids=centroids,
        n_clusters=found,
        inertia=0.0,
    )


# ---------------------------------------------------------------------------
# Cluster quality metrics
# ---------------------------------------------------------------------------


def silhouette_score(
    points: Sequence[Sequence[float]],
    labels: Sequence[int],
) -> float:
    """Mean silhouette coefficient over all non-noise points.

    For each point i:
        a(i) = mean intra-cluster distance
        b(i) = mean distance to the nearest other cluster
        s(i) = (b(i) - a(i)) / max(a(i), b(i))

    Returns the mean of s(i) ∈ [-1, 1].  Returns 0.0 when fewer than
    two distinct non-noise clusters are present.

    Points with label -1 (DBSCAN noise) are excluded from the calculation.
    """
    pts = [list(p) for p in points]
    n = len(pts)
    if n == 0:
        return 0.0

    lbls = list(labels)
    unique = {lbl for lbl in lbls if lbl >= 0}
    if len(unique) < 2:
        return 0.0

    scores: list[float] = []
    for i in range(n):
        if lbls[i] < 0:
            continue
        same = [pts[j] for j in range(n) if j != i and lbls[j] == lbls[i]]
        if same:
            a = sum(_dist(pts[i], p) for p in same) / len(same)
        else:
            a = 0.0

        b = math.inf
        for ci in unique:
            if ci == lbls[i]:
                continue
            other = [pts[j] for j in range(n) if lbls[j] == ci]
            if other:
                mean_d = sum(_dist(pts[i], p) for p in other) / len(other)
                b = min(b, mean_d)

        if b == math.inf:
            scores.append(0.0)
        else:
            denom = max(a, b)
            scores.append((b - a) / denom if denom > 0.0 else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


def davies_bouldin_index(
    points: Sequence[Sequence[float]],
    labels: Sequence[int],
) -> float:
    """Davies–Bouldin index — lower is better (0 = perfect separation).

    For each cluster i, DB(i) = max_{j≠i} (s_i + s_j) / d(c_i, c_j)
    where s_k is the average intra-cluster distance and c_k the centroid.
    The index is the mean of DB(i) over all clusters.

    Returns 0.0 when fewer than two non-noise clusters are present.
    """
    pts = [list(p) for p in points]
    n = len(pts)
    lbls = list(labels)
    unique = sorted({lbl for lbl in lbls if lbl >= 0})
    if len(unique) < 2:
        return 0.0

    clusters: dict[int, list[list[float]]] = {ci: [] for ci in unique}
    for i in range(n):
        if lbls[i] >= 0:
            clusters[lbls[i]].append(pts[i])

    centroids = {ci: _centroid(clusters[ci]) for ci in unique}
    scatter = {
        ci: (
            sum(_dist(p, centroids[ci]) for p in clusters[ci]) / len(clusters[ci])
            if clusters[ci]
            else 0.0
        )
        for ci in unique
    }

    db_sum = 0.0
    for ci in unique:
        max_ratio = 0.0
        for cj in unique:
            if ci == cj:
                continue
            d = _dist(centroids[ci], centroids[cj])
            if d == 0.0:
                continue
            ratio = (scatter[ci] + scatter[cj]) / d
            max_ratio = max(max_ratio, ratio)
        db_sum += max_ratio

    return db_sum / len(unique)
