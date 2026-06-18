"""Tests for assay_engine.algorithms.clustering."""

import pytest

from assay_engine.algorithms.clustering import (
    ClusterResult,
    Clusterer,
    agglomerative,
    davies_bouldin_index,
    dbscan,
    kmeans,
    silhouette_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BLOB_A = [[1.0, 1.0], [1.1, 0.9], [0.9, 1.1], [1.0, 1.0]]
BLOB_B = [[9.0, 9.0], [9.1, 8.9], [8.9, 9.1], [9.0, 9.0]]
TWO_BLOBS = BLOB_A + BLOB_B


# ---------------------------------------------------------------------------
# kmeans
# ---------------------------------------------------------------------------


class TestKMeans:
    def test_separates_two_blobs(self) -> None:
        result = kmeans(TWO_BLOBS, k=2, seed=0)
        labels_a = {result.labels[i] for i in range(4)}
        labels_b = {result.labels[i] for i in range(4, 8)}
        assert labels_a.isdisjoint(labels_b), "blobs should be in different clusters"

    def test_n_clusters(self) -> None:
        result = kmeans(TWO_BLOBS, k=2, seed=0)
        assert result.n_clusters == 2

    def test_centroid_count(self) -> None:
        result = kmeans(TWO_BLOBS, k=2, seed=0)
        assert len(result.centroids) == 2

    def test_inertia_positive(self) -> None:
        result = kmeans(TWO_BLOBS, k=2, seed=0)
        assert result.inertia >= 0.0

    def test_k_equals_n_trivial(self) -> None:
        pts = [[float(i)] for i in range(5)]
        result = kmeans(pts, k=5, seed=0)
        assert result.n_clusters == 5
        assert result.inertia == pytest.approx(0.0, abs=1e-9)

    def test_single_point(self) -> None:
        result = kmeans([[1.0, 2.0]], k=1, seed=0)
        assert result.labels == [0]
        assert result.n_clusters == 1

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            kmeans([], k=1)

    def test_k_too_large_raises(self) -> None:
        with pytest.raises(ValueError):
            kmeans([[1.0]], k=2)

    def test_k_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            kmeans([[1.0]], k=0)

    def test_result_type(self) -> None:
        result = kmeans([[0.0], [1.0]], k=1, seed=0)
        assert isinstance(result, ClusterResult)

    def test_protocol_compatible(self) -> None:
        def _run(fn: Clusterer, pts: list) -> ClusterResult:
            return fn(pts, k=2)

        result = _run(kmeans, TWO_BLOBS)
        assert result.n_clusters == 2


# ---------------------------------------------------------------------------
# agglomerative
# ---------------------------------------------------------------------------


class TestAgglomerative:
    def test_average_linkage_two_blobs(self) -> None:
        result = agglomerative(TWO_BLOBS, n_clusters=2, linkage="average")
        labels_a = {result.labels[i] for i in range(4)}
        labels_b = {result.labels[i] for i in range(4, 8)}
        assert labels_a.isdisjoint(labels_b)

    def test_single_linkage(self) -> None:
        result = agglomerative(TWO_BLOBS, n_clusters=2, linkage="single")
        labels_a = {result.labels[i] for i in range(4)}
        labels_b = {result.labels[i] for i in range(4, 8)}
        assert labels_a.isdisjoint(labels_b)

    def test_complete_linkage(self) -> None:
        result = agglomerative(TWO_BLOBS, n_clusters=2, linkage="complete")
        labels_a = {result.labels[i] for i in range(4)}
        labels_b = {result.labels[i] for i in range(4, 8)}
        assert labels_a.isdisjoint(labels_b)

    def test_invalid_linkage_raises(self) -> None:
        with pytest.raises(ValueError, match="linkage"):
            agglomerative(TWO_BLOBS, n_clusters=2, linkage="ward")

    def test_n_clusters_one(self) -> None:
        result = agglomerative([[0.0], [1.0], [2.0]], n_clusters=1)
        assert all(lbl == 0 for lbl in result.labels)

    def test_n_clusters_equals_n(self) -> None:
        pts = [[float(i)] for i in range(4)]
        result = agglomerative(pts, n_clusters=4)
        assert len(set(result.labels)) == 4

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            agglomerative([], n_clusters=1)


# ---------------------------------------------------------------------------
# dbscan
# ---------------------------------------------------------------------------


class TestDBSCAN:
    def test_finds_two_clusters(self) -> None:
        result = dbscan(TWO_BLOBS, eps=1.0, min_samples=2)
        # All blob A and blob B points should be in distinct non-noise clusters
        assert result.n_clusters == 2
        assert -1 not in result.labels

    def test_noise_points(self) -> None:
        # A lone outlier surrounded by two dense clusters
        pts = BLOB_A + [[50.0, 50.0]] + BLOB_B
        result = dbscan(pts, eps=1.0, min_samples=2)
        assert result.labels[4] == -1  # lone outlier is noise

    def test_all_noise(self) -> None:
        pts = [[0.0], [10.0], [20.0]]
        result = dbscan(pts, eps=0.5, min_samples=2)
        assert all(lbl == -1 for lbl in result.labels)
        assert result.n_clusters == 0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            dbscan([], eps=1.0, min_samples=2)

    def test_eps_nonpositive_raises(self) -> None:
        with pytest.raises(ValueError):
            dbscan([[0.0]], eps=0.0, min_samples=1)

    def test_min_samples_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            dbscan([[0.0]], eps=1.0, min_samples=0)


# ---------------------------------------------------------------------------
# silhouette_score
# ---------------------------------------------------------------------------


class TestSilhouetteScore:
    def test_perfect_separation(self) -> None:
        pts = BLOB_A + BLOB_B
        labels = [0] * 4 + [1] * 4
        score = silhouette_score(pts, labels)
        assert score > 0.9

    def test_one_cluster_returns_zero(self) -> None:
        pts = BLOB_A
        labels = [0] * 4
        assert silhouette_score(pts, labels) == 0.0

    def test_noise_excluded(self) -> None:
        pts = BLOB_A + BLOB_B + [[50.0, 50.0]]
        labels = [0] * 4 + [1] * 4 + [-1]
        score = silhouette_score(pts, labels)
        assert 0.0 <= score <= 1.0

    def test_empty_returns_zero(self) -> None:
        assert silhouette_score([], []) == 0.0

    def test_range(self) -> None:
        pts = [[0.0, 0.0], [1.0, 0.0], [0.5, 0.0]]
        labels = [0, 1, 0]
        score = silhouette_score(pts, labels)
        assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# davies_bouldin_index
# ---------------------------------------------------------------------------


class TestDaviesBouldinIndex:
    def test_well_separated_clusters_low_db(self) -> None:
        pts = BLOB_A + BLOB_B
        labels = [0] * 4 + [1] * 4
        db = davies_bouldin_index(pts, labels)
        assert db < 0.5

    def test_single_cluster_returns_zero(self) -> None:
        pts = BLOB_A
        labels = [0] * 4
        assert davies_bouldin_index(pts, labels) == 0.0

    def test_nonnegative(self) -> None:
        pts = [[0.0], [1.0], [5.0], [6.0]]
        labels = [0, 0, 1, 1]
        assert davies_bouldin_index(pts, labels) >= 0.0
