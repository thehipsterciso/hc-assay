"""Phase machine — the ordered stages a study moves through.

The ordering encodes the method: ingest and build the *blind* baseline before any external
claim is touched (Firewall A), and discover before confirm (Firewall B). Gates guard the
transitions between these phases.
"""

from __future__ import annotations

from enum import Enum


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
        return other.value == self.value + 1
