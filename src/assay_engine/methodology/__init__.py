"""Methodology core — the scientific contract (METHODOLOGY.md).

These are the stable, code-enforced pieces of the method:

- ``hypothesis`` — typed, falsifiable hypotheses (data-surfaced or claim-derived).
- ``verdict``    — the three verdicts: supported / contradicted / indeterminate.
- ``firewalls``  — Firewall A (claim-blindness) and Firewall B (discover/confirm),
                   enforced as runtime primitives, not docstring promises.
- ``confirm``    — confirmatory-test machinery (held-out, null/permutation, stability).
- ``preregistration`` — content-bound, time-attested pre-registration (the real lock).
- ``fence``      — the measurement ↔ interpretation boundary.
"""

from assay_engine.methodology.adjudication import (
    ClaimConfirmer,
    SourceScorecard,
    adjudicate,
)
from assay_engine.methodology.discovery import (
    HeldOutConfirmer,
    discover_and_confirm,
    subset_corpus,
)
from assay_engine.methodology.fence import Interpretation, Measurement, fence
from assay_engine.methodology.firewalls import (
    ClaimBlindGuard,
    DiscoverConfirmSplit,
    FirewallViolation,
)
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import (
    LocalHmacAuthority,
    PreRegistrationError,
    StampingAuthority,
    TimestampAuthority,
    VerifiedTimestamp,
    canonical_hypothesis_digest,
    lock_hypothesis,
    require_preregistered,
    verify_preregistration,
)
from assay_engine.methodology.verdict import Verdict, VerdictLabel

__all__ = [
    "Interpretation",
    "Measurement",
    "fence",
    "ClaimBlindGuard",
    "DiscoverConfirmSplit",
    "FirewallViolation",
    "Hypothesis",
    "HypothesisKind",
    "HypothesisOrigin",
    "Verdict",
    "VerdictLabel",
    "adjudicate",
    "SourceScorecard",
    "ClaimConfirmer",
    "discover_and_confirm",
    "subset_corpus",
    "HeldOutConfirmer",
    "LocalHmacAuthority",
    "PreRegistrationError",
    "StampingAuthority",
    "TimestampAuthority",
    "VerifiedTimestamp",
    "canonical_hypothesis_digest",
    "lock_hypothesis",
    "require_preregistered",
    "verify_preregistration",
]
