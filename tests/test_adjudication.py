"""Adjudication runner — Firewall A enforced by construction + the source scorecard (#ADR-0008).

These tests are the firewall's enforcement, not a description of it: a baseline builder that
peeks at the claims during construction must be STRUCTURALLY stopped, and the source scorecard
must honestly reflect the verdicts.
"""

import datetime as _dt

import pytest

from assay_engine.baseline.toolkit import BaselineArtifact
from assay_engine.contracts.claims import ClaimRecord
from assay_engine.contracts.schema import Corpus, Unit
from assay_engine.methodology.adjudication import adjudicate
from assay_engine.methodology.firewalls import ClaimBlindGuard, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import LocalHmacAuthority, lock_hypothesis
from assay_engine.methodology.verdict import Verdict, VerdictLabel

# A real (data-sovereign) pre-registration authority for the tests; the runner now verifies
# the lock, so hypotheses must be genuinely locked, not hand-stamped with a fake proof.
_AUTH = LocalHmacAuthority(b"adjudication-test-secret-key-0001")
# Lock comfortably in the past so it is always strictly before the runner's confirmation moment.
_LOCK_INSTANT = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(hours=1)


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
    return lock_hypothesis(
        Hypothesis(
            hypothesis_id=f"H-{claim.claim_id}",
            statement="claim holds against the baseline",
            kind=HypothesisKind.WHOLE_CORPUS,
            origin=HypothesisOrigin.EXTERNAL_CLAIM,
            test_name="adjudication",
            decision_rule="baseline corroborates the asserted relationship",
            source_claim_id=claim.claim_id,
        ),
        authority=_AUTH,
        instant=_LOCK_INSTANT,
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


def _confirmer(label_for=lambda cid: VerdictLabel.SUPPORTED):
    def confirm(hypothesis, baseline, claim):
        assert isinstance(baseline, BaselineArtifact)  # the real artifact is passed through
        # the verdict must report the hypothesis it answers (runner checks this identity)
        return Verdict(hypothesis.hypothesis_id, label_for(claim.claim_id), "r")
    return confirm


# ---- Firewall A is enforced by construction ----

def test_sneaky_builder_cannot_read_claims_during_build():
    claims = _Claims([_claim("c1")])
    with pytest.raises(FirewallViolation):
        adjudicate(
            _corpus(), claims,
            baseline_builder=_SneakyBuilder(),
            hypothesis_for=_hypothesis_for, authority=_AUTH,
            confirm=_confirmer(),
        )


def test_builder_is_handed_no_claims_source():
    # signature-level Firewall A (the honest guarantee, ADR-0008): the builder is never handed
    # a claims source and the guard it receives holds nothing — so it cannot ACCIDENTALLY
    # consult the claims. (Deliberate sys._getframe reflection into the runner's stack is out
    # of scope; only process isolation could stop that, per ADR-0008.)
    claims = _Claims([_claim("c1")])
    seen = {}

    class _InspectingBuilder:
        def build(self, corpus, *, claim_guard):
            seen["guard_holds"] = getattr(claim_guard, "_claims_source", None)
            return BaselineArtifact(corpus_fingerprint="fp", contents={})

    adjudicate(
        _corpus(), claims, baseline_builder=_InspectingBuilder(),
        hypothesis_for=_hypothesis_for, authority=_AUTH,
        confirm=_confirmer(),
    )
    assert seen["guard_holds"] is None  # the guard handed to the builder holds no claims


def test_good_builder_never_receives_claims_but_adjudication_then_sees_them():
    claims = _Claims([_claim("c1"), _claim("c2")])
    captured = {"baseline_contents": None, "confirmed": []}

    builder = _GoodBuilder()

    def confirm(hypothesis, baseline, claim):
        captured["baseline_contents"] = dict(baseline.contents)
        captured["confirmed"].append(claim.claim_id)
        return Verdict.supported(hypothesis.hypothesis_id, "r")

    baseline, scorecard = adjudicate(
        _corpus(), claims,
        baseline_builder=builder, hypothesis_for=_hypothesis_for, authority=_AUTH, confirm=confirm,
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
            hypothesis_for=discovery_hypothesis, authority=_AUTH,
            confirm=_confirmer(),
        )


# ---- claim<->hypothesis<->verdict identity (BREAK 2: no silent misattribution) ----

def test_runner_rejects_mismatched_source_claim_id():
    claims = _Claims([_claim("c1")])

    def wrong_source(claim):  # bug: hard-codes a different source_claim_id
        h = _hypothesis_for(claim)
        return Hypothesis(
            hypothesis_id=h.hypothesis_id, statement=h.statement, kind=h.kind,
            origin=h.origin, test_name=h.test_name, decision_rule=h.decision_rule,
            source_claim_id="WRONG", locked_at=h.locked_at, timestamp_proof=h.timestamp_proof,
        )

    with pytest.raises(FirewallViolation, match="misattribution"):
        adjudicate(_corpus(), claims, baseline_builder=_GoodBuilder(),
                   hypothesis_for=wrong_source, authority=_AUTH, confirm=_confirmer())


def test_runner_rejects_verdict_for_wrong_hypothesis():
    claims = _Claims([_claim("c1")])

    def mislabeled(hypothesis, baseline, claim):  # verdict reports the wrong hypothesis_id
        return Verdict.supported("SOME-OTHER-H", "r")

    with pytest.raises(FirewallViolation, match="misattribution"):
        adjudicate(_corpus(), claims, baseline_builder=_GoodBuilder(),
                   hypothesis_for=_hypothesis_for, authority=_AUTH, confirm=mislabeled)


def test_runner_rejects_unlocked_hypothesis():
    claims = _Claims([_claim("c1")])

    def unlocked(claim):  # not pre-registered: no lock/timestamp
        h = _hypothesis_for(claim)
        return Hypothesis(
            hypothesis_id=h.hypothesis_id, statement=h.statement, kind=h.kind,
            origin=h.origin, test_name=h.test_name, decision_rule=h.decision_rule,
            source_claim_id=h.source_claim_id,
        )

    with pytest.raises(FirewallViolation):  # require_locked
        adjudicate(_corpus(), claims, baseline_builder=_GoodBuilder(),
                   hypothesis_for=unlocked, authority=_AUTH, confirm=_confirmer())


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
        return Verdict(hypothesis.hypothesis_id, verdict_by[claim.claim_id], "r")

    _, sc = adjudicate(
        _corpus(), claims, baseline_builder=_GoodBuilder(),
        hypothesis_for=_hypothesis_for, authority=_AUTH, confirm=confirm, source_name="SCF-like",
    )
    assert (sc.n_supported, sc.n_contradicted, sc.n_indeterminate) == (2, 1, 1)
    assert sc.total == 4 and sc.decisive == 3
    assert sc.alignment_rate == pytest.approx(2 / 3)  # indeterminate excluded from denominator
    assert sc.source == "SCF-like"


def test_scorecard_alignment_rate_none_when_no_decisive_verdicts():
    claims = _Claims([_claim("c1")])

    def confirm(hypothesis, baseline, claim):
        return Verdict.indeterminate(hypothesis.hypothesis_id, "r")

    _, sc = adjudicate(
        _corpus(), claims, baseline_builder=_GoodBuilder(),
        hypothesis_for=_hypothesis_for, authority=_AUTH, confirm=confirm,
    )
    assert sc.alignment_rate is None and sc.n_indeterminate == 1


def test_adjudicate_runs_with_no_claims():
    _, sc = adjudicate(
        _corpus(), _Claims([]), baseline_builder=_GoodBuilder(),
        hypothesis_for=_hypothesis_for, authority=_AUTH,
        confirm=_confirmer(),
    )
    assert sc.total == 0 and sc.alignment_rate is None


def test_guard_release_blocked_while_sealed_directly():
    # the structural primitive the runner relies on, asserted directly
    guard = ClaimBlindGuard(_Claims([]))
    with guard.sealed():
        with pytest.raises(FirewallViolation):
            guard.release()
    assert guard.release() is not None
