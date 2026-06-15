"""Feature-builder interface — optional dataset-specific features.

The baseline toolkit provides generic builders (embeddings, similarity, etc.). When a
dataset has features only meaningful in its own domain, an adapter supplies them through a
:class:`FeatureBuilder`. Output is a plain numeric :class:`FeatureMatrix` keyed by unit id,
so the engine consumes it without knowing what the features mean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from assay_engine.contracts.schema import Corpus


@dataclass(frozen=True, slots=True)
class FeatureMatrix:
    """Numeric features for a set of units. ``rows[i]`` corresponds to ``unit_ids[i]``."""

    unit_ids: tuple[str, ...]
    feature_names: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if len(self.rows) != len(self.unit_ids):
            raise ValueError("FeatureMatrix row count must match unit_ids length")
        width = len(self.feature_names)
        if any(len(r) != width for r in self.rows):
            raise ValueError("FeatureMatrix rows must match feature_names width")


class FeatureBuilder(Protocol):
    """Build dataset-specific numeric features from a canonical corpus."""

    def build(self, corpus: Corpus) -> FeatureMatrix:
        """Compute features for (a subset of) the corpus units. Must be deterministic."""
        ...

    @property
    def provides(self) -> Sequence[str]:
        """Names of the features this builder produces (for provenance)."""
        ...
