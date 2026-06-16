"""Adjudication runner — the engine owns the firewall guarantee, not each study (ADR-0008).

METHODOLOGY.md describes the adjudication pipeline: build a baseline *blind* to the external
claims (Firewall A), convert each claim into a typed, pre-stated hypothesis, test each against
the blind baseline, and *score the external source* against the validated baseline (§5). Until
now the engine shipped the parts (a custodial :class:`ClaimBlindGuard`, the confirmatory tests,
the verdicts) but no composition — so Firewall A held only if a study wired it correctly by
hand. For a blueprint inherited by many studies, that pushes the single most important
methodological guarantee onto every cloner, where it is easy to get silently wrong (build the
baseline with the claims in scope and nothing stops you).

:func:`adjudicate` makes the guarantee structural: it builds the baseline *inside* a sealed
claim-guard that holds the claims source, so the baseline builder cannot reach the claims
during construction (any attempt raises ``FirewallViolation``); only after the baseline is
built does the runner release the claims and adjudicate. It then aggregates the verdicts into a
:class:`SourceScorecard` — the §5 "score the source" step, expressed as alignment *frequency*
on decisive claims, explicitly NOT a normative judgement of the source's quality (richer
dimensions — where it aligns, diverges, leaves gaps — are data-surfaced downstream, per §5).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable, Protocol

from assay_engine.contracts.claims import ClaimRecord, ExternalClaimsSource
from assay_engine.contracts.schema import Corpus
from assay_engine.methodology.firewalls import ClaimBlindGuard, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisOrigin
from assay_engine.methodology.preregistration import (
    TimestampAuthority,
    require_preregistered,
)
from assay_engine.methodology.verdict import Verdict, VerdictLabel

if TYPE_CHECKING:
    # Annotations only — importing baseline at runtime would invert the layering
    # (baseline.toolkit depends on methodology.firewalls) and create a cycle.
    from assay_engine.baseline.toolkit import BaselineArtifact, BaselineBuilder


class ClaimConfirmer(Protocol):
    """Study-supplied: confirm one claim-derived hypothesis against the (blind) baseline.

    The study owns this because only it knows the baseline's structure and how a given claim
    maps onto a measurement of it; the engine supplies the confirmatory primitives
    (``confirm_whole_corpus`` / ``confirm_unit_level``) the study uses inside it.
    """

    def __call__(
        self, hypothesis: Hypothesis, baseline: BaselineArtifact, claim: ClaimRecord
    ) -> Verdict: ...


@dataclass(frozen=True, slots=True)
class SourceScorecard:
    """How an external source aligns with the independent baseline (METHODOLOGY.md §5).

    ``alignment_rate`` is supported / (supported + contradicted) — the fraction of *decisive*
    claims where the blind baseline agrees with the source's assertion. ``indeterminate`` is
    excluded from the denominator (the method could not decide; counting it would understate
    or overstate alignment). This is a frequency, not a verdict on whether the source is
    "good": it says how often an independent reading of the data corroborates the source.
    """

    source: str
    n_supported: int
    n_contradicted: int
    n_indeterminate: int
    alignment_rate: float | None
    verdicts: tuple[Verdict, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return self.n_supported + self.n_contradicted + self.n_indeterminate

    @property
    def decisive(self) -> int:
        return self.n_supported + self.n_contradicted


def _score(source: str, verdicts: list[Verdict]) -> SourceScorecard:
    counts = {
        VerdictLabel.SUPPORTED: 0,
        VerdictLabel.CONTRADICTED: 0,
        VerdictLabel.INDETERMINATE: 0,
    }
    for v in verdicts:
        counts[v.label] += 1
    decisive = counts[VerdictLabel.SUPPORTED] + counts[VerdictLabel.CONTRADICTED]
    rate = counts[VerdictLabel.SUPPORTED] / decisive if decisive else None
    return SourceScorecard(
        source=source,
        n_supported=counts[VerdictLabel.SUPPORTED],
        n_contradicted=counts[VerdictLabel.CONTRADICTED],
        n_indeterminate=counts[VerdictLabel.INDETERMINATE],
        alignment_rate=rate,
        verdicts=tuple(verdicts),
    )


def adjudicate(
    corpus: Corpus,
    claims_source: ExternalClaimsSource,
    *,
    baseline_builder: BaselineBuilder,
    hypothesis_for: Callable[[ClaimRecord], Hypothesis],
    confirm: ClaimConfirmer,
    authority: TimestampAuthority,
    source_name: str = "external",
) -> tuple[BaselineArtifact, SourceScorecard]:
    """Run the full adjudication, enforcing Firewall A by construction.

    1. The claims source is kept in this function's local scope and is NOT handed to the
       builder; the baseline is built inside a sealed :class:`ClaimBlindGuard` that holds
       nothing. This is a **signature-level** guarantee: the builder is never *handed* a
       claims source by the engine, so it cannot accidentally consult the claims. It is NOT
       frame isolation — a builder that deliberately reflects into this runner's call stack
       (``sys._getframe``) could reach ``claims_source``; preventing that would require
       running the builder in a separate process, which is out of scope. The guarantee is
       against *accidental* circularity, not against a builder that willfully defeats the
       firewall.
    2. After the baseline exists, each claim is mapped (by ``hypothesis_for``) to its typed,
       pre-stated ``EXTERNAL_CLAIM`` hypothesis whose ``source_claim_id`` must match the claim
       and which must be genuinely **pre-registered** — :func:`~assay_engine.methodology.
       preregistration.require_preregistered` checks (via the supplied ``authority``) that the
       proof binds this hypothesis's content and that its attested lock time precedes the
       **baseline build** (the ordering instant is captured before the build). A claim-derived
       hypothesis must therefore be locked *before* ``adjudicate`` is called — ``hypothesis_for``
       looks up an already-locked hypothesis; locking on demand inside it (after the baseline
       exists) is rejected, so the hypothesis cannot have been tuned to the baseline.
    3. The verdict's ``hypothesis_id`` must match the hypothesis it answers (no misattribution),
       and the verdicts are aggregated into a :class:`SourceScorecard`.

    ``authority`` is the pre-registration timestamp authority (e.g.
    :class:`~assay_engine.methodology.preregistration.LocalHmacAuthority`, or an RFC-3161
    adapter); the engine ships no silent-accept default, so a study must supply a real one.

    Returns ``(baseline, scorecard)``. Raises ``FirewallViolation`` (incl.
    :class:`~assay_engine.methodology.preregistration.PreRegistrationError`) on any
    claim↔hypothesis↔verdict identity mismatch, a non-``EXTERNAL_CLAIM`` (data-surfaced)
    hypothesis, or a hypothesis that is not verifiably pre-registered before confirmation.
    """
    # The claims source stays in THIS function's local scope and is never given to the builder.
    # The builder receives a guard holding nothing (a blind-mode signal only), so there is no
    # object reachable from the builder that contains the claims — not even via the guard's
    # internals. This is stronger than a custodial guard, whose private `_claims_source` a
    # determined builder could read past the sealed `release()` check (adversarial review).
    # Captured BEFORE the baseline is built: an EXTERNAL_CLAIM hypothesis derives from the
    # external claim, not from the baseline, so it must be pre-registered before the baseline (the
    # answer) exists. Using this as `not_after` makes "lock before the result is in hand" real —
    # a hypothesis locked on demand inside `hypothesis_for` (i.e. after the build) is rejected,
    # forcing studies to pre-lock their claim-derived hypotheses (#83).
    not_after = _dt.datetime.now(tz=_dt.timezone.utc)

    guard: ClaimBlindGuard[ExternalClaimsSource] = ClaimBlindGuard()
    with guard.sealed():
        baseline = baseline_builder.build(corpus, claim_guard=guard)

    scorecard = adjudicate_with_baseline(
        baseline,
        claims_source.claims(),
        hypothesis_for=hypothesis_for,
        confirm=confirm,
        authority=authority,
        not_after=not_after,
        source_name=source_name,
    )
    return baseline, scorecard


def adjudicate_with_baseline(
    baseline: BaselineArtifact,
    claims: "Iterable[ClaimRecord]",
    *,
    hypothesis_for: Callable[[ClaimRecord], Hypothesis],
    confirm: ClaimConfirmer,
    authority: TimestampAuthority,
    not_after: _dt.datetime,
    source_name: str = "external",
    on_step: "Callable[[Hypothesis, Verdict], None] | None" = None,
) -> SourceScorecard:
    """Adjudicate a **materialized claim set** against an already-built blind baseline (core).

    Factored out of :func:`adjudicate` so a composed pipeline that builds the baseline once
    (and shares it with discovery) can reuse the identical, hardened Firewall-A loop instead of
    rebuilding the baseline. The caller is responsible for having built ``baseline`` blind and
    for passing the ``not_after`` ordering instant captured *before* that build — so the
    lock-before-baseline guarantee is preserved across the shared-baseline composition.

    ``claims`` is **materialized once** here (not re-pulled from a source): a caller that gated
    or recorded a claim snapshot must adjudicate *that* snapshot, not a set a re-iterable source
    could change between the gate and the scoring (adversarial review #95). Enforces the same
    claim↔hypothesis↔verdict identity + pre-registration checks as :func:`adjudicate`.
    """
    verdicts: list[Verdict] = []
    materialized = list(claims)  # claims used only after the blind baseline is built
    # within-run identity uniqueness: a repeated claim_id would be counted once per occurrence in
    # _score, inflating the scorecard denominator and biasing alignment_rate (#138).
    seen_claim_ids: set[str] = set()
    for c in materialized:
        if c.claim_id in seen_claim_ids:
            raise FirewallViolation(
                f"duplicate claim_id {c.claim_id!r} within one adjudication run — claim identity "
                "must be unique (a repeat would inflate the scorecard denominator)"
            )
        seen_claim_ids.add(c.claim_id)
    for claim in materialized:
        hypothesis = hypothesis_for(claim)
        if hypothesis.origin is not HypothesisOrigin.EXTERNAL_CLAIM:
            raise FirewallViolation(
                f"claim {claim.claim_id!r} produced a {hypothesis.origin.value!r} hypothesis; "
                "adjudicated claims must be EXTERNAL_CLAIM (pre-stated, not data-surfaced)"
            )
        if hypothesis.source_claim_id != claim.claim_id:
            raise FirewallViolation(
                f"hypothesis for claim {claim.claim_id!r} carries source_claim_id "
                f"{hypothesis.source_claim_id!r} — claim↔hypothesis misattribution"
            )
        # Pre-registration: the proof must bind THIS hypothesis's content (no post-lock content
        # swap) and its attested lock time must precede the baseline build (so the claim-derived
        # hypothesis cannot have been tuned to the baseline).
        require_preregistered(hypothesis, authority=authority, not_after=not_after)
        verdict = confirm(hypothesis, baseline, claim)
        if verdict.hypothesis_id != hypothesis.hypothesis_id:
            raise FirewallViolation(
                f"verdict for hypothesis {hypothesis.hypothesis_id!r} reports hypothesis_id "
                f"{verdict.hypothesis_id!r} — hypothesis↔verdict misattribution"
            )
        verdicts.append(verdict)
        if on_step is not None:
            # per-claim hook (in order) so a caller can record the pre-registered hypothesis AND
            # its verdict to provenance as each happens, not in a post-hoc batch (#93).
            on_step(hypothesis, verdict)

    return _score(source_name, verdicts)
