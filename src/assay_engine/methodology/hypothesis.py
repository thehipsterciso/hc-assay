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
from typing import Any, Literal, Mapping

from assay_engine._frozen import freeze_mapping

# The tail a claim predicts the statistic lies in, relative to the null.
Direction = Literal["greater", "less"]


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
    pre-registration. An unlocked hypothesis (either field ``None``) must not be passed to a
    confirmatory test.

    Scope of ``locked`` (audit pass 1, issue #6): ``locked`` is only a cheap **presence**
    predicate — both fields populated. It is NOT the methodology-grade check and carries no
    cryptographic meaning on its own. The real pre-registration verification —
    content-binding (the proof covers this hypothesis's content), timestamp attestation, and
    lock-before-confirm ordering — lives in
    :mod:`assay_engine.methodology.preregistration` (``verify_preregistration`` /
    ``require_preregistered``), and the confirmatory runners (:mod:`adjudication`,
    :mod:`discovery`) enforce it via a supplied ``TimestampAuthority``. Use
    :func:`~assay_engine.methodology.preregistration.lock_hypothesis` to produce a hypothesis
    whose lock actually verifies; a hand-set ``timestamp_proof`` string satisfies ``locked``
    but will fail ``verify_preregistration``.
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
    # The predicted direction, fixed at pre-registration so it cannot be chosen post-hoc
    # after seeing the baseline (audit pass 2, issue #24). For an EXTERNAL_CLAIM hypothesis
    # the adapter derives this from the claim's assertion, not from the baseline.
    predicted_direction: Direction | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    @property
    def locked(self) -> bool:
        return self.locked_at is not None and self.timestamp_proof is not None

    def __post_init__(self) -> None:
        if self.origin is HypothesisOrigin.EXTERNAL_CLAIM and not self.source_claim_id:
            raise ValueError("EXTERNAL_CLAIM hypotheses must carry a source_claim_id")
        object.__setattr__(self, "params", freeze_mapping(self.params))
