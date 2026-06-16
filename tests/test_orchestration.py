"""Phase machine + governance gates (audit pass 1: #9, #11, #17)."""

import pytest

from assay_engine.contracts.study import StudyMode
from assay_engine.orchestration.gates import Gate, GateDecision, GateError
from assay_engine.orchestration.phases import Phase, legal_transition, required_phases

DISCOVERY = frozenset({StudyMode.DISCOVERY})
ADJUDICATE = frozenset({StudyMode.ADJUDICATE_EXTERNAL_CLAIMS})


# ---- phases (#9) ----

def test_can_advance_to_is_strict_full_pipeline_adjacency():
    assert Phase.INGEST.can_advance_to(Phase.BASELINE)
    assert not Phase.CONFIRM.can_advance_to(Phase.REPORT)
    assert not Phase.BASELINE.can_advance_to(Phase.INGEST)  # no backward
    assert not Phase.INGEST.can_advance_to(Phase.DISCOVERY)  # no skip


def test_required_phases_depend_on_mode():
    assert Phase.ADJUDICATE not in required_phases(DISCOVERY)
    assert Phase.SCORE not in required_phases(DISCOVERY)
    assert required_phases(ADJUDICATE)[-1] is Phase.REPORT
    assert Phase.ADJUDICATE in required_phases(ADJUDICATE)


def test_discovery_only_study_can_reach_report():
    # issue #9(a): the dead path is fixed — CONFIRM->REPORT is legal for discovery-only
    assert legal_transition(Phase.CONFIRM, Phase.REPORT, DISCOVERY)


def test_discovery_only_study_cannot_enter_adjudication():
    # issue #9(b): a blind discovery study must never be routed into external-claims phases
    assert not legal_transition(Phase.CONFIRM, Phase.ADJUDICATE, DISCOVERY)


def test_adjudicate_only_study_skips_the_discovery_spine():
    # modes are independent: an adjudicate-only study goes BASELINE->ADJUDICATE->SCORE->REPORT
    # and never enters the discovery spine (DISCOVERY/PREREGISTER/CONFIRM).
    assert legal_transition(Phase.BASELINE, Phase.ADJUDICATE, ADJUDICATE)
    assert legal_transition(Phase.ADJUDICATE, Phase.SCORE, ADJUDICATE)
    assert not legal_transition(Phase.CONFIRM, Phase.ADJUDICATE, ADJUDICATE)  # no CONFIRM phase
    assert not legal_transition(Phase.BASELINE, Phase.DISCOVERY, ADJUDICATE)


def test_combined_study_follows_full_path():
    both = DISCOVERY | ADJUDICATE
    assert legal_transition(Phase.CONFIRM, Phase.ADJUDICATE, both)
    assert legal_transition(Phase.ADJUDICATE, Phase.SCORE, both)
    assert not legal_transition(Phase.CONFIRM, Phase.REPORT, both)


# ---- gates (#11) ----

def _approve(_ctx):
    return GateDecision(approved=True, gate="g", reason="ok")


def _block(_ctx):
    return GateDecision(approved=False, gate="g", reason="precondition failed")


def test_gate_passes_legal_approved_transition():
    g = Gate("g", Phase.INGEST, Phase.BASELINE, _approve)
    assert g.evaluate({}).approved


def test_gate_rejects_illegal_transition_for_its_modes():
    # discovery gate declaring a transition into ADJUDICATE is illegal
    g = Gate("g", Phase.CONFIRM, Phase.ADJUDICATE, _approve, modes=DISCOVERY)
    with pytest.raises(GateError):
        g.evaluate({})


def test_gate_blocks_on_failed_precondition():
    g = Gate("g", Phase.INGEST, Phase.BASELINE, _block)
    with pytest.raises(GateError):
        g.evaluate({})


def test_requires_human_gate_fails_loud_without_recorder():
    # issue #11: a human-in-the-loop gate cannot pass without a provenance recorder
    g = Gate("g", Phase.INGEST, Phase.BASELINE, _approve, requires_human=True)
    with pytest.raises(GateError):
        g.evaluate({})


def test_requires_human_gate_records_when_recorder_supplied():
    recorded = []
    g = Gate("g", Phase.INGEST, Phase.BASELINE, _approve, requires_human=True)
    decision = g.evaluate({}, record=recorded.append)
    assert decision.approved
    assert recorded and recorded[0].gate == "g"


def test_gate_rejects_transition_illegal_for_running_study_modes():
    # issue #23: even a default-(ALL_MODES) gate must respect the running study's modes
    g = Gate("g", Phase.CONFIRM, Phase.ADJUDICATE, _approve)  # default modes
    assert g.evaluate({}).approved  # legal under the full pipeline
    with pytest.raises(GateError):
        g.evaluate({}, study_modes=DISCOVERY)  # discovery-only run forbids ADJUDICATE
