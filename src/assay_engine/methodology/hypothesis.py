"""Typed, falsifiable hypotheses (METHODOLOGY.md §3).

Every hypothesis names what is claimed, the test, the data it runs on, and a pre-specified
decision rule. Two origins:

- ``DISCOVERY`` — surfaced by the data, then made specific, locked, and timestamped before
  confirmation (Firewall B).
- ``EXTERNAL_CLAIM`` — derived by the adapter from an external expert claim, tested against
  the blind baseline (Firewall A).

Two kinds, which select the confirmation mechanism:

- ``UNIT_LEVEL`` — confirmed on a held-out split.
- ``WHOLE_CORPUS`` — no held-out object possible; confirmed against null/permutation
  distributions and stability across resamples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class HypothesisKind(Enum):
    UNIT_LEVEL = "unit_level"
    WHOLE_CORPUS = "whole_corpus"


class HypothesisOrigin(Enum):
    DISCOVERY = "discovery"
    EXTERNAL_CLAIM = "external_claim"


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A locked, falsifiable assertion ready for confirmatory testing.

    ``locked_at`` and ``timestamp_proof`` are populated when the hypothesis is sealed for
    pre-registration (RFC-3161 token reference). An unlocked hypothesis (both ``None``) must
    not be passed to a confirmatory test — the engine enforces this at the gate, and the
    ``locked`` property is the in-code check.
    """

    hypothesis_id: str
    statement: str
    kind: HypothesisKind
    origin: HypothesisOrigin
    test_name: str
    decision_rule: str
    source_claim_id: str | None = None
    locked_at: str | None = None
    timestamp_proof: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    @property
    def locked(self) -> bool:
        return self.locked_at is not None and self.timestamp_proof is not None

    def __post_init__(self) -> None:
        if self.origin is HypothesisOrigin.EXTERNAL_CLAIM and not self.source_claim_id:
            raise ValueError("EXTERNAL_CLAIM hypotheses must carry a source_claim_id")
