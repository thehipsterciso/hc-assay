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
from assay_engine.provenance import ProvenanceError, ProvenanceTrail, from_records, verify_records
from assay_engine.pipeline import StudyPlan, StudyResult, auto_approve, run_study
from tests import reference_study as ref

ALL = frozenset(StudyMode)
DISCOVERY = frozenset({StudyMode.DISCOVERY})
ADJUDICATE = frozenset({StudyMode.ADJUDICATE_EXTERNAL_CLAIMS})


def _fixed_clock():
    t = _dt.datetime(2026, 6, 16, 12, 0, 0, tzinfo=_dt.timezone.utc)
    return lambda: t


def _run(tmp_path, modes, **kw) -> StudyResult:
    src = ref.write_source(tmp_path / "corpus.json")
    kw.setdefault("gate_handler", auto_approve)  # gate_handler is required; default to opt-out
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
        {
            "seq": e.seq,
            "kind": e.kind,
            "summary": e.summary,
            "payload": dict(e.payload),
            "timestamp": e.timestamp,
            "prev_hash": e.prev_hash,
            "entry_hash": e.entry_hash,
        }
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


def test_parser_returning_non_corpus_raises_ingestion_error(tmp_path):
    # #134: a misimplemented parser that returns a non-Corpus (None/list/dict) must surface the
    # documented IngestionError, not an opaque AttributeError at `corpus.units`.
    from assay_engine.pipeline import IngestionError

    class _NoneParser:
        def parse(self, source):
            return None  # forgot to return a Corpus

        def source_fingerprint(self, source):
            return "fp"

    plan = ref.make_plan(ref.write_source(tmp_path / "c.json"), modes=DISCOVERY)
    bad_defn = replace(plan.definition, parser=_NoneParser())
    with pytest.raises(IngestionError, match="expected Corpus"):
        run_study(replace(plan, definition=bad_defn), gate_handler=auto_approve)


def test_gate_review_payload_is_immutable_but_json_serializable(tmp_path):
    # #141: GateReview.payload is a deep-frozen FrozenDict (immutable, #113) — but the public
    # operator-review extension point must still be serializable. payload_dict() thaws it so an
    # operator can json.dumps the review without a custom encoder.
    import json

    from assay_engine.pipeline import GateReview

    review = GateReview(
        gate="g",
        frm=Phase.PREREGISTER,
        to=Phase.CONFIRM,
        summary="s",
        payload={"hypothesis_ids": ["h1", "h2"], "nested": {"k": 1}},
    )
    # raw payload is frozen (immutable) and NOT directly json-serializable
    with pytest.raises(TypeError):
        json.dumps(review.payload)
    # the thawed view round-trips through json cleanly
    out = json.loads(json.dumps(review.payload_dict()))
    assert out == {"hypothesis_ids": ["h1", "h2"], "nested": {"k": 1}}


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
            return [
                ClaimRecord(
                    claim_id=cid, subject=cid, referents=(cid,), assertion={"expected": "high"}
                )
            ]

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
    assert seen["ids"] == ["c-A"]  # the gate reviewed the materialized snapshot
    assert scored == {"H-c-A"}  # and exactly that snapshot was scored (not c-B)


def test_duplicate_claim_ids_are_rejected(tmp_path):
    # #138: a claims source repeating a claim_id would inflate the scorecard denominator — the
    # runner must reject it rather than count the same claim N times.
    from assay_engine.contracts.claims import ClaimRecord

    dup = type(
        "Dup",
        (),
        {
            "claims": lambda self: [
                ClaimRecord(claim_id="c1", subject="c1", referents=("c1",), assertion={"e": 1}),
                ClaimRecord(claim_id="c1", subject="c1", referents=("c1",), assertion={"e": 1}),
            ],
            "claim_fingerprint": lambda self: "fp",
        },
    )()
    plan = ref.make_plan(ref.write_source(tmp_path / "c.json"), modes=ADJUDICATE)
    plan = replace(plan, definition=replace(plan.definition, claims_source=dup))
    with pytest.raises(FirewallViolation, match="duplicate claim_id"):
        run_study(plan, gate_handler=auto_approve)


def test_recorded_claim_fingerprint_is_engine_computed_over_scored_claims(tmp_path):
    # #137: the recorded claim_fingerprint must be the engine's own hash of the EXACT claims
    # scored — not the source's unverified self-report. A source lying about its fingerprint must
    # not corrupt the trail's claim identity.
    from assay_engine.contracts.claims import ClaimRecord
    from assay_engine.pipeline import _engine_claim_fingerprint

    records = [
        ClaimRecord(claim_id="c1", subject="c1", referents=("c1",), assertion={"e": "high"}),
        ClaimRecord(claim_id="c2", subject="c2", referents=("c2",), assertion={"e": "low"}),
    ]
    lying = type(
        "Lying",
        (),
        {"claims": lambda self: list(records), "claim_fingerprint": lambda self: "0" * 64},
    )()
    plan = ref.make_plan(ref.write_source(tmp_path / "c.json"), modes=ADJUDICATE)
    plan = replace(plan, definition=replace(plan.definition, claims_source=lying))
    seen = {}

    def handler(review):
        seen.update(review.payload_dict())
        return GateDecision(approved=True, gate=review.gate, reason="ok")

    run_study(plan, gate_handler=handler)
    assert seen["claim_fingerprint"] == _engine_claim_fingerprint(records)  # engine-computed
    assert seen["source_reported_claim_fingerprint"] == "0" * 64  # self-report kept for cross-check
    assert seen["claim_fingerprint_matches_source"] is False  # mismatch surfaced, not hidden


def test_empty_claims_source_fails_loud(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=ADJUDICATE)
    # swap in a claims source that yields nothing
    empty = type("E", (), {"claims": lambda self: [], "claim_fingerprint": lambda self: "fp"})()
    plan = replace(plan, definition=replace(plan.definition, claims_source=empty))
    with pytest.raises(ValueError, match="no claims"):
        run_study(plan, gate_handler=auto_approve)


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
        return [
            Hypothesis(
                hypothesis_id="H",
                statement="x",
                kind=HypothesisKind.WHOLE_CORPUS,
                origin=HypothesisOrigin.DISCOVERY,
                test_name="t",
                decision_rule="r",
            )
        ]

    with pytest.raises(PreRegistrationError):
        run_study(replace(plan, discover=bad_discover), gate_handler=auto_approve)


def test_baseline_not_matching_corpus_is_rejected(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)

    class WrongBaseline:
        def build(self, corpus, *, claim_guard):
            from assay_engine.baseline.toolkit import BaselineArtifact

            return BaselineArtifact(corpus_fingerprint="WRONG", contents={"x": 1})

    with pytest.raises(FirewallViolation, match="corpus_fingerprint"):
        run_study(replace(plan, baseline_builder=WrongBaseline()), gate_handler=auto_approve)


def test_confirm_misattribution_is_rejected(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    with pytest.raises(FirewallViolation, match="misattribution"):
        run_study(
            replace(plan, confirm_held_out=lambda h, c: Verdict.supported("WRONG-ID", "r")),
            gate_handler=auto_approve,
        )


# ---- wired seams: versioner, tracker, feature builders, secret, validation ----


def test_versioner_records_retrievable_source_version(tmp_path):
    from assay_engine.persistence.versioning import LocalDataVersioner

    vsn = LocalDataVersioner(store_dir=str(tmp_path / "store"))
    res = _run(tmp_path, DISCOVERY, versioner=vsn)
    assert res.source_version and vsn.path_for(res.source_version).exists()
    assert any(e.payload.get("source_version") == res.source_version for e in res.provenance)


def test_tracker_receives_run_and_metrics_and_failures_dont_abort(tmp_path):
    class FakeTracker:
        def __init__(self):
            self.calls = []

        def start_run(self, name, params):
            self.calls.append(("start", name))
            return "run-1"

        def log_metric(self, run_id, key, value):
            self.calls.append(("metric", key, value))

        def log_artifact(self, run_id, path):
            self.calls.append(("artifact", path))

        def end_run(self, run_id, status="FINISHED"):
            self.calls.append(("end", run_id, status))

    t = FakeTracker()
    res = _run(tmp_path, ALL, tracker=t)
    assert res.experiment_run_id == "run-1"
    assert ("start", "reference-study") in t.calls and ("end", "run-1", "FINISHED") in t.calls
    assert any(c[0] == "metric" and c[1] == "alignment_rate" for c in t.calls)

    class BoomTracker(FakeTracker):
        def log_metric(self, *a):
            raise RuntimeError("tracker down")

    res2 = _run(tmp_path, ADJUDICATE, tracker=BoomTracker())  # must NOT abort the run
    assert res2.scorecard is not None
    assert any(e.kind == "tracking_error" for e in res2.provenance)


def test_failed_run_records_failure_entry_and_marks_tracker_failed(tmp_path):
    # #109 + #110: a raised run leaves a 'run_failed' provenance entry AND ends the tracker run
    # as FAILED (distinguishable from success).
    from assay_engine.provenance import ProvenanceTrail

    class T:
        def __init__(self):
            self.ended = None

        def start_run(self, name, params):
            return "r"

        def log_metric(self, *a):
            pass

        def log_artifact(self, *a):
            pass

        def end_run(self, run_id, status="FINISHED"):
            self.ended = status

    def reject(r):
        return GateDecision(approved=False, gate=r.gate, reason="halt")

    src = ref.write_source(tmp_path / "c.json")
    trail = ProvenanceTrail()
    t = T()
    with pytest.raises(GateError):
        run_study(ref.make_plan(src, modes=DISCOVERY), gate_handler=reject, tracker=t, trail=trail)
    assert t.ended == "FAILED"
    failed = [e for e in trail.entries if e.kind == "run_failed"]
    assert failed and failed[0].payload["error_type"] == "GateError"


def test_tracing_setup_failure_still_ends_the_tracker_run(tmp_path, monkeypatch):
    # #156: if tracing bootstrap raises AFTER the tracker run started, the finally must still run
    # end_run — an already-started run must not leak in RUNNING state. Pre-fix the bootstrap ran
    # outside the try, so end_run was never reached.
    import assay_engine.pipeline as pl

    class T:
        def __init__(self):
            self.ended = None

        def start_run(self, name, params):
            return "r"

        def log_metric(self, *a):
            pass

        def log_artifact(self, *a):
            pass

        def end_run(self, run_id, status="FINISHED"):
            self.ended = status

    def boom():
        raise RuntimeError("tracing bootstrap exploded")

    monkeypatch.setattr(pl, "bootstrap_tracing", boom)
    t = T()
    with pytest.raises(RuntimeError, match="tracing bootstrap exploded"):
        _run(tmp_path, DISCOVERY, tracker=t)
    assert t.ended == "FAILED"  # the started run was ended, not leaked RUNNING (#156)


def test_feature_builders_are_computed_and_recorded(tmp_path):
    from assay_engine.contracts.features import FeatureMatrix

    class LenFeatures:
        def build(self, corpus):
            return FeatureMatrix(
                unit_ids=tuple(u.unit_id for u in corpus.units),
                feature_names=("text_len",),
                rows=tuple((float(len(u.text)),) for u in corpus.units),
            )

        @property
        def provides(self):
            return ("text_len",)

    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    plan = replace(plan, definition=replace(plan.definition, feature_builders=(LenFeatures(),)))
    res = run_study(plan, gate_handler=auto_approve)
    assert len(res.feature_matrices) == 1 and res.feature_matrices[0].feature_names == ("text_len",)
    assert any(e.kind == "features" for e in res.provenance)


def test_feature_matrix_with_ghost_unit_ids_is_rejected(tmp_path):
    from assay_engine.contracts.features import FeatureMatrix

    class GhostFeatures:
        def build(self, corpus):
            return FeatureMatrix(
                unit_ids=("ghost1", "ghost2"), feature_names=("f",), rows=((1.0,), (2.0,))
            )

        @property
        def provides(self):
            return ("f",)

    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    plan = replace(plan, definition=replace(plan.definition, feature_builders=(GhostFeatures(),)))
    with pytest.raises(FirewallViolation, match="absent from the corpus"):
        run_study(plan, gate_handler=auto_approve)


def test_split_ids_absent_from_corpus_are_rejected(tmp_path):
    from assay_engine.methodology.firewalls import DiscoverConfirmSplit

    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    bad = DiscoverConfirmSplit.from_partition({"u0", "ghost"}, {"u3", "u4"})
    with pytest.raises(FirewallViolation, match="absent from the corpus"):
        run_study(replace(plan, split=bad), gate_handler=auto_approve)


def test_bad_source_raises_ingestion_error(tmp_path):
    from assay_engine.pipeline import IngestionError

    plan = ref.make_plan(tmp_path / "does-not-exist.json", modes=DISCOVERY)
    with pytest.raises(IngestionError):
        run_study(plan, gate_handler=auto_approve)


def test_secret_keys_the_provenance_trail(tmp_path):
    secret = b"run-study-provenance-secret-0001"
    res = _run(tmp_path, DISCOVERY, secret=secret)
    verify_records(res.provenance, secret=secret)  # verifies with the key
    with pytest.raises(ProvenanceError):
        verify_records(res.provenance)  # and not without it


def test_secret_and_trail_are_mutually_exclusive(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    with pytest.raises(ValueError, match="either a caller-owned trail OR a secret"):
        run_study(
            ref.make_plan(src, modes=DISCOVERY),
            gate_handler=auto_approve,
            secret=b"x" * 16,
            trail=ProvenanceTrail(),
        )


def test_gate_handler_is_required(tmp_path):
    src = ref.write_source(tmp_path / "c.json")
    with pytest.raises(TypeError):
        run_study(ref.make_plan(src, modes=DISCOVERY))  # type: ignore[call-arg]


def test_run_study_rejects_claim_hypothesis_locked_after_baseline(tmp_path):
    # #126: end-to-end through run_study, a claim hypothesis locked AFTER the baseline existed
    # must be rejected (not_after=baseline_instant). The reference locks in the past (accepted);
    # here we lock on-demand at now() inside hypothesis_for → must raise.
    from assay_engine.methodology.preregistration import lock_hypothesis

    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=ADJUDICATE)

    def lock_now(claim):
        h = Hypothesis(
            hypothesis_id=f"H-{claim.claim_id}",
            statement="s",
            kind=HypothesisKind.WHOLE_CORPUS,
            origin=HypothesisOrigin.EXTERNAL_CLAIM,
            test_name="t",
            decision_rule="r",
            source_claim_id=claim.claim_id,
            predicted_direction="greater",
        )
        return lock_hypothesis(
            h, authority=ref.AUTHORITY
        )  # default instant = now() (after baseline)

    with pytest.raises(PreRegistrationError, match="precede|strictly before"):
        run_study(replace(plan, hypothesis_for=lock_now), gate_handler=auto_approve)


def test_gate_review_payload_is_frozen_and_hashable(tmp_path):
    # #113: GateReview's Mapping payload must be deep-frozen (immutable + hashable)
    from assay_engine._frozen import FrozenDict
    from assay_engine.pipeline import GateReview

    r = GateReview(
        gate="g",
        frm=Phase.PREREGISTER,
        to=Phase.CONFIRM,
        summary="s",
        payload={"a": {"b": 1}, "ids": [1, 2]},
    )
    assert isinstance(r.payload, FrozenDict)
    with pytest.raises(Exception):  # noqa: B017 — any mutation must fail
        r.payload["a"] = 2  # type: ignore[index]
    hash(r)  # frozen record is hashable


def test_run_study_correlates_spans_to_run_id(tmp_path):
    # #122: every phase span must see the run's assay.run_id baggage (traces correlate to the run)
    pytest.importorskip("opentelemetry")
    from contextlib import contextmanager

    from opentelemetry import baggage

    class CapturingTracer:
        def __init__(self):
            self.seen = set()

        @contextmanager
        def span(self, name, attributes=None, *, kind="CHAIN"):
            self.seen.add(baggage.get_baggage("assay.run_id"))
            yield

    class T:
        def start_run(self, name, params):
            return "run-xyz"

        def log_metric(self, *a):
            pass

        def log_artifact(self, *a):
            pass

        def end_run(self, run_id, status="FINISHED"):
            pass

    tracer = CapturingTracer()
    _run(tmp_path, DISCOVERY, tracer=tracer, tracker=T())
    assert tracer.seen == {"run-xyz"}  # all phase spans saw the run id; none None
    assert baggage.get_baggage("assay.run_id") is None  # detached after the run


def test_plan_validates_required_callables_per_mode():
    src = type("P", (), {})()  # unused; __post_init__ fires before any run
    from assay_engine.contracts.study import StudyDefinition

    defn = StudyDefinition.discovery("s", ref.ReferenceParser(), ("q",))
    with pytest.raises(ValueError, match="DISCOVERY mode requires"):
        StudyPlan(
            definition=defn,
            source=src,
            baseline_builder=ref.ReferenceBaselineBuilder(),
            authority=ref.AUTHORITY,
        )  # missing split/discover/confirm_held_out


def test_plan_validates_adjudication_callables():
    from assay_engine.contracts.study import StudyDefinition

    defn = StudyDefinition(
        name="s",
        modes=ADJUDICATE,
        parser=ref.ReferenceParser(),
        research_questions=("q",),
        claims_source=ref.ReferenceClaims(),
    )
    with pytest.raises(ValueError, match="ADJUDICATE_EXTERNAL_CLAIMS mode requires"):
        StudyPlan(
            definition=defn,
            source=type("P", (), {})(),
            baseline_builder=ref.ReferenceBaselineBuilder(),
            authority=ref.AUTHORITY,
        )


def test_empty_corpus_raises_ingestion_error(tmp_path):
    from assay_engine.contracts.schema import Corpus
    from assay_engine.pipeline import IngestionError

    class EmptyParser:
        def parse(self, source):
            return Corpus(units=())

        def source_fingerprint(self, source):
            return "empty"

    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    plan = replace(plan, definition=replace(plan.definition, parser=EmptyParser()))
    with pytest.raises(IngestionError, match="empty corpus"):
        run_study(plan, gate_handler=auto_approve)


def test_tracker_start_and_end_failures_are_swallowed(tmp_path):
    class Cranky:
        def start_run(self, name, params):
            raise RuntimeError("start boom")

        def log_metric(self, *a):
            pass

        def log_artifact(self, *a):
            pass

        def end_run(self, run_id, status="FINISHED"):
            raise RuntimeError("end boom")

    # start_run failing -> run_id stays None, run still completes; end_run failure swallowed
    res = _run(tmp_path, DISCOVERY, tracker=Cranky())
    assert res.experiment_run_id is None
    assert any(e.kind == "tracking_error" for e in res.provenance)


def test_empty_discovery_partition_rejected(tmp_path):
    from assay_engine.methodology.firewalls import DiscoverConfirmSplit

    src = ref.write_source(tmp_path / "c.json")
    plan = ref.make_plan(src, modes=DISCOVERY)
    # valid (in-corpus) but empty discovery partition -> subset yields no units
    empty_disc = DiscoverConfirmSplit.from_partition(set(), {"u3", "u4", "u5"})
    with pytest.raises(FirewallViolation, match="discovery partition selects no corpus units"):
        run_study(replace(plan, split=empty_disc), gate_handler=auto_approve)
