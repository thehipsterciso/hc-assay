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
        # Enforce the numeric type contract the docstring promises: a non-numeric cell (a str,
        # None, NaN) from a misimplemented builder would otherwise flow into baseline math and
        # surface as an opaque downstream error. bool is excluded (it is an int subclass but not
        # a feature value). NaN/inf are rejected as not finite numeric features (#149).
        import math

        for i, r in enumerate(self.rows):
            for v in r:
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise TypeError(
                        f"FeatureMatrix.rows[{i}] contains a non-numeric value {v!r} "
                        f"({type(v).__name__}); features must be int/float"
                    )
                if not math.isfinite(v):
                    raise ValueError(f"FeatureMatrix.rows[{i}] contains a non-finite value {v!r}")


class FeatureBuilder(Protocol):
    """Build dataset-specific numeric features from a canonical corpus."""

    def build(self, corpus: Corpus) -> FeatureMatrix:
        """Compute features for (a subset of) the corpus units. Must be deterministic."""
        ...

    @property
    def provides(self) -> Sequence[str]:
        """Names of the features this builder produces (for provenance)."""
        ...
