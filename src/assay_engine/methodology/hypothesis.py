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
    # Decision thresholds, optionally pre-registered so they cannot be chosen post-hoc after
    # seeing the null/baseline (pass 5, #H-001 — the threshold analogue of predicted_direction).
    # When set, they are bound into the pre-registration digest and the confirmers cross-check the
    # confirm-time argument against them (a mismatch raises), so a pre-registered confirmatory test
    # commits its alpha / stability bar in advance. Left None for exploratory/opted-out use.
    alpha: float | None = None
    stability_threshold: float | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    @property
    def locked(self) -> bool:
        return self.locked_at is not None and self.timestamp_proof is not None

    def __post_init__(self) -> None:
        if self.origin is HypothesisOrigin.EXTERNAL_CLAIM and not self.source_claim_id:
            raise ValueError("EXTERNAL_CLAIM hypotheses must carry a source_claim_id")
        # Validate pre-registered thresholds at construction (#H-001) so an invalid value can never
        # be bound into a proof: alpha is a one-sided level in (0, 0.5); stability is a fraction in
        # (0, 1]. (Mirrors the confirmers' own bounds checks.)
        if self.alpha is not None and not (0.0 < self.alpha < 0.5):
            raise ValueError(f"alpha must be in (0, 0.5); got {self.alpha}")
        if self.stability_threshold is not None and not (0.0 < self.stability_threshold <= 1.0):
            raise ValueError(
                f"stability_threshold must be in (0, 1]; got {self.stability_threshold}"
            )
        # Validate predicted_direction at the earliest possible point (pass 3, #F-002): an
        # invalid tail ("up", "UP", "") must never reach lock_hypothesis (which would
        # cryptographically bind garbage into the proof) nor confirm_unit_level (which does not
        # otherwise re-validate it). Only the two recognized tails — or None (deferred to
        # confirm time on the whole-corpus path) — are admissible.
        if self.predicted_direction is not None and self.predicted_direction not in (
            "greater",
            "less",
        ):
            raise ValueError(
                "predicted_direction must be 'greater' or 'less' (or None); got "
                f"{self.predicted_direction!r} — an unrecognized tail would silently flip the "
                "supported/contradicted verdict"
            )
        object.__setattr__(self, "params", freeze_mapping(self.params))
