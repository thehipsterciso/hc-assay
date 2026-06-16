"""Baseline toolkit — dataset-agnostic raw material for the independent reference.

Generic, deterministic building blocks for a baseline: similarity/distance and descriptive
statistics (``primitives``), plus the reproducibility harness that hashes inputs, derives
seeds, records component versions, and stamps a :class:`BaselineArtifact`'s determinism record
(``determinism``, ADR-0001). Everything here is pure and dependency-free; determinism is
mandatory (METHODOLOGY.md §1).

The choice-bearing, heavy builders (which embedding model, which clustering algorithm, which
graph construction) encode dataset/study decisions and are supplied by a study's adapter as
:class:`BaselineBuilder` implementations — the engine provides the contract and the
reproducibility harness, not the modeling choices (ADR-0002).
"""

from assay_engine.baseline.determinism import (
    DeterminismRecord,
    build_baseline_artifact,
    corpus_fingerprint,
    hash_value,
    stable_seed,
)
from assay_engine.baseline.primitives import (
    cosine_similarity,
    cosine_similarity_matrix,
    descriptive_stats,
    euclidean_distance,
)
from assay_engine.baseline.toolkit import BaselineArtifact, BaselineBuilder

__all__ = [
    "BaselineArtifact",
    "BaselineBuilder",
    "DeterminismRecord",
    "build_baseline_artifact",
    "corpus_fingerprint",
    "hash_value",
    "stable_seed",
    "cosine_similarity",
    "cosine_similarity_matrix",
    "descriptive_stats",
    "euclidean_distance",
]
