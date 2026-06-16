"""Phase machine — the ordered stages a study moves through.

The ordering encodes the method: ingest and build the *blind* baseline before any external
claim is touched (Firewall A), and discover before confirm (Firewall B). Gates guard the
transitions between these phases.

Mode coupling (audit pass 1, issue #9): the legal phase sequence depends on the study's
modes, which are independent. A discovery-only study runs INGEST→BASELINE→DISCOVERY→
PREREGISTER→CONFIRM→REPORT and must *not* enter the external-claims phases (ADJUDICATE,
SCORE); an adjudicate-only study runs INGEST→BASELINE→ADJUDICATE→SCORE→REPORT and never enters
the discovery spine; a combined study runs the full sequence. Use :func:`required_phases` /
:func:`legal_transition` for mode-aware legality; :meth:`Phase.can_advance_to` is the
mode-agnostic full-pipeline adjacency check.
"""

from __future__ import annotations

from enum import Enum

from assay_engine.contracts.study import StudyMode


class Phase(Enum):
    """Ordered analysis phases. Value is the sort key used to forbid backward transitions."""

    INGEST = 1            # raw source → canonical corpus
    BASELINE = 2          # build the independent baseline, blind to any claims (Firewall A)
    DISCOVERY = 3         # data surfaces candidate hypotheses
    PREREGISTER = 4       # lock + timestamp hypotheses before confirmation
    CONFIRM = 5           # confirmatory tests on held-out / null distributions (Firewall B)
    ADJUDICATE = 6        # convert external claims to verdicts against the blind baseline
    SCORE = 7             # score the external source against the validated baseline
    REPORT = 8            # assemble the reproducibility package

    def can_advance_to(self, other: "Phase") -> bool:
        """Adjacent in the *full* pipeline (mode-agnostic). For mode-aware legality that lets
        a discovery-only study skip ADJUDICATE/SCORE, use :func:`legal_transition`."""
        return other.value == self.value + 1


def required_phases(modes: frozenset[StudyMode]) -> tuple[Phase, ...]:
    """The ordered phases a study with ``modes`` actually visits.

    The two modes are independent (a study may declare either or both). INGEST and BASELINE
    always run; the discovery spine (DISCOVERY→PREREGISTER→CONFIRM) runs only in DISCOVERY mode;
    the external-claims phases (ADJUDICATE→SCORE) run only in adjudication mode; REPORT always
    closes. So an adjudicate-only study goes INGEST→BASELINE→ADJUDICATE→SCORE→REPORT and never
    enters the discovery spine (it derives hypotheses from claims, not from the data).
    """
    seq = [Phase.INGEST, Phase.BASELINE]
    if StudyMode.DISCOVERY in modes:
        seq += [Phase.DISCOVERY, Phase.PREREGISTER, Phase.CONFIRM]
    if StudyMode.ADJUDICATE_EXTERNAL_CLAIMS in modes:
        seq += [Phase.ADJUDICATE, Phase.SCORE]
    seq.append(Phase.REPORT)
    return tuple(seq)


def legal_transition(frm: Phase, to: Phase, modes: frozenset[StudyMode]) -> bool:
    """True iff ``to`` immediately follows ``frm`` in the phase sequence for ``modes``.

    A discovery-only study therefore legally goes CONFIRM→REPORT and can never enter
    ADJUDICATE/SCORE; an adjudication study goes CONFIRM→ADJUDICATE→SCORE→REPORT.
    """
    seq = required_phases(modes)
    try:
        i = seq.index(frm)
    except ValueError:
        return False
    return i + 1 < len(seq) and seq[i + 1] == to
