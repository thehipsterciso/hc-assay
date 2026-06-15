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

from dataclasses import dataclass, field
from typing import Any, Generic, Mapping, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Measurement(Generic[T]):
    """A value produced purely by the engine from data — no judgment involved."""

    value: T
    produced_by: str
    inputs_hash: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Interpretation(Generic[T]):
    """A judgment *about* one or more measurements. Downstream-only; never an input upstream."""

    value: T
    basis: tuple[str, ...]  # ids/refs of the measurements this interprets
    rationale: str
    judged_by: str  # e.g. "operator" or a model identifier — judgment is always labeled
    metadata: Mapping[str, Any] = field(default_factory=dict)


def fence(measurement: Measurement[Any], value: T, *, rationale: str, judged_by: str) -> Interpretation[T]:
    """Cross the fence once, in the only permitted direction: measurement → interpretation."""
    return Interpretation(
        value=value,
        basis=(measurement.produced_by,),
        rationale=rationale,
        judged_by=judged_by,
        metadata={"inputs_hash": measurement.inputs_hash},
    )
