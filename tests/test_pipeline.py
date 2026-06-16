"""Study runner — the composed end-to-end pipeline (ADR-0010).

Drives the engine's run_study over the synthetic reference adapter (tests/reference_study.py),
asserting the workflow composes correctly AND that its methodological/governance invariants hold
by construction: phase order, blind baseline, pre-registration before confirm, the governance
gate, and an append-only, tamper-evident provenance trail.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import replace

import pytest

from assay_engine.contracts.study import StudyMode
from assay_engine.methodology.firewalls import FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import PreRegistrationError
from assay_engine.methodology.verdict import Verdict
from assay_engine.orchestration.gates import GateDecision, GateError
from assay_engine.orchestration.phases import Phase, required_phases
from assay_engine.provenance import ProvenanceError, from_records, verify_records
from assay_engine.pipeline import StudyPlan, StudyResult, run_study
from tests import reference_study as ref

ALL = frozenset(StudyMode)
DISCOVERY = frozenset({StudyMode.DISCOVERY})
ADJUDICATE = frozenset({StudyMode.ADJUDICATE_EXTERNAL_CLAIMS})


def _fixed_clock():
    t = _dt.datetime(2026, 6, 16, 12, 0, 0, tzinfo=_dt.timezone.utc)
    return lambda: t


def _run(tmp_path, modes, **kw) -> StudyResult:
    src = ref.write_source(tmp_path / "corpus.json")
    return run_study(ref.make_plan(src, modes=modes), **kw)


# ---- the workflow composes, both modes ----

def test_discovery_only_runs_end_to_end(tmp_path):
    res = _run(tmp_path, DISCOVERY)
    assert res.phases == required_phases(DISCOVERY)
    assert Phase.ADJUDICATE not in res.phases and Phase.SCORE not in res.phases
    assert [v.hypothesis_id for v in res.discovery_verdicts] == ["H-disc-1"]
    assert res.scorecard is None
    res_verify_ok(res)


def test_adjudicate_only_runs_end_to_end(tmp_path):
    res = _run(tmp_path, ADJUDICATE)
    assert res.phases == required_phases(ADJUDICATE)
    assert Phase.DISCOVERY not in res.phases
    assert res.discovery_verdicts == ()
    assert res.scorecard is not None and res.scorecard.total == 2
    res_verify_ok(res)


def test_combined_modes_run_all_phases(tmp_path):
    res = _run(tmp_path, ALL)
    assert res.phases == required_phases(ALL)
    assert res.discovery_verdicts and res.scorecard is not None
    res_verify_ok(res)


def res_verify_ok(res: StudyResult) -> None:
    verify_records(res.provenance)  # the trail is an intact hash chain
    kinds = [e.kind for e in res.provenance]
    assert kinds[0] == "run_start" and kinds[-1] == "report"  # closes with the report record
    # the REPORT phase was entered before the report record was written
    assert any(e.kind == "phase" and e.payload["phase"] == "REPORT" for e in res.provenance)
    assert res.baseline.corpus_fingerprint == res.corpus_fingerprint


# ---- provenance: append-only + tamper-evident ----

def test_provenance_roundtrips_and_detects_tampering(tmp_path):
    res = _run(tmp_path, DISCOVERY)
    records = tuple(
        {"seq": e.seq, "kind": e.kind, "summary": e.summary, "payload": dict(e.payload),
         "timestamp": e.timestamp, "prev_hash": e.prev_hash, "entry_hash": e.entry_hash}
        for e in res.provenance
    )
    assert from_records(records)  # intact chain rebuilds fine
    # edit a payload deep in the chain -> hash mismatch detected
    bad = list(records)
    bad[2] = {**bad[2], "summary": "TAMPERED"}
    with pytest.raises(ProvenanceError):
        from_records(bad)
    # drop an entry -> reorder/linkage detected
    with pytest.raises(ProvenanceError):
        from_records(records[:3] + records[4:])


def test_provenance_is_deterministic_under_fixed_clock(tmp_path):
    a = _run(tmp_path, DISCOVERY, clock=_fixed_clock())
    b = _run(tmp_path, DISCOVERY, clock=_fixed_clock())
    assert [e.entry_hash for e in a.provenance] == [e.entry_hash for e in b.provenance]


def test_provenance_records_baseline_and_each_verdict(tmp_path):
    res = _run(tmp_path, ALL)
    kinds = [e.kind for e in res.provenance]
    assert "baseline" in kinds and "discovery" in kinds and "score" in kinds
    assert sum(1 for k in kinds if k == "verdict") == 1 + 2  # 1 discovery + 2 adjudication


# ---- the governance gate is real ----

def test_gate_rejection_halts_before_confirm(tmp_path):
    def reject(r):
        return GateDecision(approved=False, gate=r.gate, reason="operator rejected")
    with pytest.raises(GateError, match="blocked PREREGISTER->CONFIRM"):
        _run(tmp_path, DISCOVERY, gate_handler=reject)


def test_adjudication_is_also_gated(tmp_path):
    # #86: adjudication is a confirmatory step and must be gated too — a rejecting handler halts
    # an adjudicate-only run before any claim is scored.
    def reject(r):
        return GateDecision(approved=False, gate=r.gate, reason="rejected")
    with pytest.raises(GateError, match="review-baseline-and-claims"):
        _run(tmp_path, ADJUDICATE, gate_handler=reject)


def test_every_confirmatory_path_invokes_a_gate(tmp_path):
    seen = []
    def handler(review):
        seen.append(review.gate)
        return GateDecision(approved=True, gate=review.gate, reason="ok")
    _run(tmp_path, ADJUDICATE, gate_handler=handler)
    assert "review-baseline-and-claims" in seen  # adjudicate-only path is gated
    seen.clear()
    _run(tmp_path, ALL, gate_handler=handler)
    assert seen == ["review-locked-hypotheses", "review-baseline-and-claims"]


def test_adjudication_scores_the_gated_claim_snapshot_not_a_remutated_source(tmp_path):
    # #95: a source returning different claims on successive .claims() calls must NOT let the gate
    # review one set while a different set is scored. The runner materializes once and scores that.
    from assay_engine.contracts.claims import ClaimRecord
    calls = {"n": 0}

    class Mutating:
        def claims(self):
            calls["n"] += 1
            cid = "c-A" if calls["n"] == 1 else "c-B"
            return [ClaimRecord(claim_id=cid, subject=cid, referents=(cid,),
                                assertion={"expected": "high"})]
        def claim_fingerprint(self):
            return "fp"

    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=ADJUDICATE)
    plan = replace(plan, definition=replace(plan.definition, claims_source=Mutating()))
    seen = {}
    def handler(review):
        seen["ids"] = list(review.payload["claim_ids"])
        return GateDecision(approved=True, gate=review.gate, reason="ok")
    res = run_study(plan, gate_handler=handler)
    scored = {v.hypothesis_id for v in res.scorecard.verdicts}
    assert seen["ids"] == ["c-A"]       # the gate reviewed the materialized snapshot
    assert scored == {"H-c-A"}          # and exactly that snapshot was scored (not c-B)


def test_empty_claims_source_fails_loud(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=ADJUDICATE)
    # swap in a claims source that yields nothing
    empty = type("E", (), {"claims": lambda self: [], "claim_fingerprint": lambda self: "fp"})()
    plan = replace(plan, definition=replace(plan.definition, claims_source=empty))
    with pytest.raises(ValueError, match="no claims"):
        run_study(plan)


def test_adjudication_records_per_claim_preregistration(tmp_path):
    res = _run(tmp_path, ADJUDICATE)
    pre = [e for e in res.provenance if e.kind == "preregister"]
    assert {e.payload["hypothesis_id"] for e in pre} == {"H-c1", "H-c2"}  # one per claim
    assert all("source_claim_id" in e.payload for e in pre)


def test_caller_owned_trail_survives_a_raise(tmp_path):
    from assay_engine.provenance import ProvenanceTrail
    trail = ProvenanceTrail()
    def reject(r):
        return GateDecision(approved=False, gate=r.gate, reason="halt")
    src = ref.write_source(tmp_path / "c.json")
    with pytest.raises(GateError):
        run_study(ref.make_plan(src, modes=DISCOVERY), gate_handler=reject, trail=trail)
    # the partial trail — including the blocking gate decision — is auditable after the raise
    kinds = [e.kind for e in trail.entries]
    assert "baseline" in kinds
    gate = [e for e in trail.entries if e.kind == "gate"][-1]
    assert gate.payload["approved"] is False


def test_gate_handler_sees_locked_hypotheses(tmp_path):
    seen = {}
    def handler(review):
        seen["ids"] = list(review.payload["hypothesis_ids"])
        seen["transition"] = (review.frm, review.to)
        return GateDecision(approved=True, gate=review.gate, reason="ok")
    _run(tmp_path, DISCOVERY, gate_handler=handler)
    assert seen["ids"] == ["H-disc-1"]
    assert seen["transition"] == (Phase.PREREGISTER, Phase.CONFIRM)


# ---- methodological invariants enforced by the runner ----

def test_unlocked_discovery_hypothesis_is_rejected(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    def bad_discover(corpus):
        return [Hypothesis(hypothesis_id="H", statement="x", kind=HypothesisKind.WHOLE_CORPUS,
                           origin=HypothesisOrigin.DISCOVERY, test_name="t", decision_rule="r")]
    with pytest.raises(PreRegistrationError):
        run_study(replace(plan, discover=bad_discover))


def test_baseline_not_matching_corpus_is_rejected(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    class WrongBaseline:
        def build(self, corpus, *, claim_guard):
            from assay_engine.baseline.toolkit import BaselineArtifact
            return BaselineArtifact(corpus_fingerprint="WRONG", contents={"x": 1})
    with pytest.raises(FirewallViolation, match="corpus_fingerprint"):
        run_study(replace(plan, baseline_builder=WrongBaseline()))


def test_confirm_misattribution_is_rejected(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    with pytest.raises(FirewallViolation, match="misattribution"):
        run_study(replace(plan, confirm_held_out=lambda h, c: Verdict.supported("WRONG-ID", "r")))


def test_plan_validates_required_callables_per_mode():
    src = type("P", (), {})()  # unused; __post_init__ fires before any run
    from assay_engine.contracts.study import StudyDefinition
    defn = StudyDefinition.discovery("s", ref.ReferenceParser(), ("q",))
    with pytest.raises(ValueError, match="DISCOVERY mode requires"):
        StudyPlan(definition=defn, source=src, baseline_builder=ref.ReferenceBaselineBuilder(),
                  authority=ref.AUTHORITY)  # missing split/discover/confirm_held_out
