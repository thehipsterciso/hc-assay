"""Adjudication runner — Firewall A enforced by construction + the source scorecard (#ADR-0008).

These tests are the firewall's enforcement, not a description of it: a baseline builder that
peeks at the claims during construction must be STRUCTURALLY stopped, and the source scorecard
must honestly reflect the verdicts.
"""

import pytest

from assay_engine.baseline.toolkit import BaselineArtifact
from assay_engine.contracts.claims import ClaimRecord
from assay_engine.contracts.schema import Corpus, Unit
from assay_engine.methodology.adjudication import adjudicate
from assay_engine.methodology.firewalls import ClaimBlindGuard, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.verdict import Verdict, VerdictLabel


class _Claims:
    """A minimal ExternalClaimsSource over a fixed list of claims."""

    def __init__(self, claims):
        self._claims = claims

    def claims(self):
        return list(self._claims)

    def claim_fingerprint(self):
        return "claims-fp"


def _claim(cid, supported=True):
    # 'assertion.expected' carries what the source asserts; the confirmer compares to baseline.
    return ClaimRecord(
        claim_id=cid, subject=cid, referents=(cid,),
        assertion={"expected": "high" if supported else "low"},
    )


def _corpus():
    return Corpus(units=(Unit("a", "x"), Unit("b", "y")))


def _hypothesis_for(claim: ClaimRecord) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=f"H-{claim.claim_id}",
        statement="claim holds against the baseline",
        kind=HypothesisKind.WHOLE_CORPUS,
        origin=HypothesisOrigin.EXTERNAL_CLAIM,
        test_name="adjudication",
        decision_rule="baseline corroborates the asserted relationship",
        source_claim_id=claim.claim_id,
        locked_at="2026-06-16T00:00:00Z",
        timestamp_proof="rfc3161:demo",
    )


class _GoodBuilder:
    """A well-behaved baseline builder: uses only the corpus, never the claims."""

    def build(self, corpus, *, claim_guard):
        return BaselineArtifact(corpus_fingerprint="fp", contents={"n_units": len(corpus.units)})


class _SneakyBuilder:
    """A builder that tries to peek at the claims during construction — must be stopped."""

    def build(self, corpus, *, claim_guard):
        claim_guard.release()  # Firewall A violation: claims are sealed during the build
        return BaselineArtifact(corpus_fingerprint="fp", contents={})


def _confirmer(verdict_for):
    def confirm(hypothesis, baseline, claim):
        # the baseline must be the real artifact; assert the firewall didn't strip it
        assert isinstance(baseline, BaselineArtifact)
        return verdict_for(claim.claim_id)
    return confirm


# ---- Firewall A is enforced by construction ----

def test_sneaky_builder_cannot_read_claims_during_build():
    claims = _Claims([_claim("c1")])
    with pytest.raises(FirewallViolation):
        adjudicate(
            _corpus(), claims,
            baseline_builder=_SneakyBuilder(),
            hypothesis_for=_hypothesis_for,
            confirm=_confirmer(lambda cid: Verdict.supported(cid, "r")),
        )


def test_builder_has_no_reachable_reference_to_claims():
    # the strongest form of Firewall A: even a builder that inspects the guard's internals
    # finds no claims — the source is never in the builder's reach (only the runner's scope).
    claims = _Claims([_claim("c1")])
    seen = {}

    class _InspectingBuilder:
        def build(self, corpus, *, claim_guard):
            seen["custodial"] = getattr(claim_guard, "_claims_source", None)
            return BaselineArtifact(corpus_fingerprint="fp", contents={})

    adjudicate(
        _corpus(), claims, baseline_builder=_InspectingBuilder(),
        hypothesis_for=_hypothesis_for,
        confirm=_confirmer(lambda cid: Verdict.supported(cid, "r")),
    )
    assert seen["custodial"] is None  # the guard holds nothing; claims unreachable from build


def test_good_builder_never_receives_claims_but_adjudication_then_sees_them():
    claims = _Claims([_claim("c1"), _claim("c2")])
    captured = {"baseline_contents": None, "confirmed": []}

    builder = _GoodBuilder()

    def confirm(hypothesis, baseline, claim):
        captured["baseline_contents"] = dict(baseline.contents)
        captured["confirmed"].append(claim.claim_id)
        return Verdict.supported(claim.claim_id, "r")

    baseline, scorecard = adjudicate(
        _corpus(), claims,
        baseline_builder=builder, hypothesis_for=_hypothesis_for, confirm=confirm,
        source_name="src",
    )
    assert captured["baseline_contents"] == {"n_units": 2}  # baseline built from corpus only
    assert captured["confirmed"] == ["c1", "c2"]            # claims adjudicated AFTER the build
    assert scorecard.total == 2


def test_non_external_claim_hypothesis_is_rejected():
    claims = _Claims([_claim("c1")])

    def discovery_hypothesis(claim):  # wrong: a data-surfaced hypothesis, not a pre-stated claim
        h = _hypothesis_for(claim)
        return Hypothesis(
            hypothesis_id=h.hypothesis_id, statement=h.statement, kind=h.kind,
            origin=HypothesisOrigin.DISCOVERY, test_name=h.test_name,
            decision_rule=h.decision_rule, locked_at=h.locked_at,
            timestamp_proof=h.timestamp_proof,
        )

    with pytest.raises(FirewallViolation, match="EXTERNAL_CLAIM"):
        adjudicate(
            _corpus(), claims, baseline_builder=_GoodBuilder(),
            hypothesis_for=discovery_hypothesis,
            confirm=_confirmer(lambda cid: Verdict.supported(cid, "r")),
        )


# ---- the source scorecard (METHODOLOGY.md §5) ----

def test_scorecard_counts_and_alignment_rate_excludes_indeterminate():
    verdict_by = {
        "c1": VerdictLabel.SUPPORTED,
        "c2": VerdictLabel.SUPPORTED,
        "c3": VerdictLabel.CONTRADICTED,
        "c4": VerdictLabel.INDETERMINATE,
    }
    claims = _Claims([_claim(c) for c in verdict_by])

    def confirm(hypothesis, baseline, claim):
        return Verdict(claim.claim_id, verdict_by[claim.claim_id], "r")

    _, sc = adjudicate(
        _corpus(), claims, baseline_builder=_GoodBuilder(),
        hypothesis_for=_hypothesis_for, confirm=confirm, source_name="SCF-like",
    )
    assert (sc.n_supported, sc.n_contradicted, sc.n_indeterminate) == (2, 1, 1)
    assert sc.total == 4 and sc.decisive == 3
    assert sc.alignment_rate == pytest.approx(2 / 3)  # indeterminate excluded from denominator
    assert sc.source == "SCF-like"


def test_scorecard_alignment_rate_none_when_no_decisive_verdicts():
    claims = _Claims([_claim("c1")])

    def confirm(hypothesis, baseline, claim):
        return Verdict.indeterminate(claim.claim_id, "r")

    _, sc = adjudicate(
        _corpus(), claims, baseline_builder=_GoodBuilder(),
        hypothesis_for=_hypothesis_for, confirm=confirm,
    )
    assert sc.alignment_rate is None and sc.n_indeterminate == 1


def test_adjudicate_runs_with_no_claims():
    _, sc = adjudicate(
        _corpus(), _Claims([]), baseline_builder=_GoodBuilder(),
        hypothesis_for=_hypothesis_for,
        confirm=_confirmer(lambda cid: Verdict.supported(cid, "r")),
    )
    assert sc.total == 0 and sc.alignment_rate is None


def test_guard_release_blocked_while_sealed_directly():
    # the structural primitive the runner relies on, asserted directly
    guard = ClaimBlindGuard(_Claims([]))
    with guard.sealed():
        with pytest.raises(FirewallViolation):
            guard.release()
    assert guard.release() is not None
