"""The measurement ↔ interpretation fence (METHODOLOGY.md §6).

A hard boundary separates **measurement** (numbers the engine produces) from
**interpretation** (what they mean). Interpretation lives strictly downstream and cannot
feed back into measurement. Any use of judgment — including LLM-assisted classification — is
interpretation, and is labeled as such.

These wrappers make the boundary explicit and type-visible in the pipeline. ``fence`` turns
a measurement into an interpretation; there is deliberately no inverse — you cannot turn an
interpretation back into a measurement.
"""

from __future__ import annotations

from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass, field
from typing import Any, Generic, Mapping, TypeVar

from assay_engine._frozen import freeze, freeze_mapping

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Interpretation(Generic[T]):
    """A judgment *about* one or more measurements. Downstream-only; never an input upstream."""

    value: T
    basis: tuple[str, ...]  # refs (producer:inputs_hash) of the measurements this interprets
    rationale: str
    judged_by: str  # e.g. "operator" or a model identifier — judgment is always labeled
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze the payload so the frozen record is deeply immutable + hashable (issue #29).
        object.__setattr__(self, "value", freeze(self.value))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


def _contains_interpretation(obj: Any) -> bool:
    """True if ``obj`` is, or recursively contains, an :class:`Interpretation`."""
    if isinstance(obj, Interpretation):
        return True
    if isinstance(obj, AbcMapping):
        return any(_contains_interpretation(v) for v in obj.values())
    if isinstance(obj, (list, tuple, set, frozenset)):
        return any(_contains_interpretation(v) for v in obj)
    return False


@dataclass(frozen=True, slots=True)
class Measurement(Generic[T]):
    """A value produced purely by the engine from data — no judgment involved."""

    value: T
    produced_by: str
    inputs_hash: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Structurally close the one-way fence: an interpretation may never re-enter as a
        # measurement value — at the top level OR nested in a container/metadata (issues #22,
        # #30). Note: ref/inputs_hash integrity (forgery resistance) is delegated to the
        # provenance/audit layer, not enforced here.
        if _contains_interpretation(self.value) or _contains_interpretation(self.metadata):
            raise TypeError(
                "Measurement value/metadata must not contain an Interpretation — "
                "interpretation must not feed back into measurement (the fence)"
            )
        # Freeze the payload so the frozen record is deeply immutable + hashable (issue #29).
        object.__setattr__(self, "value", freeze(self.value))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    @property
    def ref(self) -> str:
        """A stable id for this specific measurement: producer + input hash."""
        return f"{self.produced_by}:{self.inputs_hash}"


def fence(
    measurement: Measurement[Any], value: T, *, rationale: str, judged_by: str
) -> Interpretation[T]:
    """Cross the fence once, in the only permitted direction: measurement → interpretation.

    ``basis`` records the specific measurement's ``ref`` (``producer:inputs_hash``), so an
    interpretation can be traced to the exact measurement it interprets — not merely to the
    producer (audit pass 1, issue #16).
    """
    return Interpretation(
        value=value,
        basis=(measurement.ref,),
        rationale=rationale,
        judged_by=judged_by,
        metadata={"inputs_hash": measurement.inputs_hash},
    )
