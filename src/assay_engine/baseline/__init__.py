"""Baseline toolkit — dataset-agnostic builders for the independent reference.

Generic raw material for any baseline: embeddings, similarity/distance structure,
graph/topology, clustering, descriptive statistics. Everything here operates on the
canonical :class:`~assay_engine.contracts.schema.Corpus` (and optional
:class:`~assay_engine.contracts.features.FeatureMatrix`) and knows nothing about what the
data means. Determinism is mandatory: fixed seeds, hashed inputs, recorded model/version
(METHODOLOGY.md §1).
"""

from assay_engine.baseline.toolkit import BaselineArtifact, BaselineBuilder

__all__ = ["BaselineArtifact", "BaselineBuilder"]
