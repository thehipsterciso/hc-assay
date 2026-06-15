"""Governance gates — deterministic, code-enforced transition checks.

A gate guards a transition between phases. It evaluates code-enforced preconditions (the
firewalls, lock state) and, where the governance model requires it, a recorded human
approval. A gate cannot be silently bypassed: a transition is legal only if the gate returns
an ``approved`` decision, and a ``requires_human`` gate refuses to pass unless a provenance
recorder is supplied to capture the decision (audit pass 1, issue #11).

Current scope: this module implements the precondition check, mode-aware transition legality
(issue #9), and the fail-loud provenance/human-approval hook. The append-only provenance
*store* and the interactive human-approval UI are wired by the orchestration layer when it
lands; until then, a ``requires_human`` gate fails loud rather than silently approving, and
the recorder is the seam that store will plug into. The strong present-tense guarantees in
GOVERNANCE.md describe that wired end-state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from assay_engine._frozen import freeze_mapping
from assay_engine.contracts.study import StudyMode
from assay_engine.orchestration.phases import Phase, legal_transition

ALL_MODES: frozenset[StudyMode] = frozenset(StudyMode)
ProvenanceRecorder = Callable[["GateDecision"], None]


class GateError(RuntimeError):
    """Raised when a transition is attempted through a gate that did not approve it."""


@dataclass(frozen=True, slots=True)
class GateDecision:
    approved: bool
    gate: str
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", freeze_mapping(self.evidence))


@dataclass(frozen=True, slots=True)
class Gate:
    """A guard on the transition ``frm -> to``.

    ``precondition`` is a pure, code-enforced check over the run context returning a
    :class:`GateDecision`. ``modes`` scopes which study modes this gate applies to (default:
    the full pipeline). ``requires_human`` marks gates that additionally need a recorded
    operator approval, which is enforced fail-loud at :meth:`evaluate`.
    """

    name: str
    frm: Phase
    to: Phase
    precondition: Callable[[Mapping[str, Any]], GateDecision]
    requires_human: bool = False
    modes: frozenset[StudyMode] = ALL_MODES

    def evaluate(
        self,
        context: Mapping[str, Any],
        *,
        record: ProvenanceRecorder | None = None,
    ) -> GateDecision:
        if not legal_transition(self.frm, self.to, self.modes):
            raise GateError(
                f"gate {self.name!r} declares an illegal transition for its modes: "
                f"{self.frm.name} -> {self.to.name}"
            )
        decision = self.precondition(context)
        if not decision.approved:
            raise GateError(f"gate {self.name!r} blocked transition: {decision.reason}")
        if self.requires_human and record is None:
            # Fail loud: a human-in-the-loop gate must not pass without a recorder to
            # capture the approval to the (eventual) append-only provenance trail.
            raise GateError(
                f"gate {self.name!r} requires recorded human approval but no provenance "
                "recorder was supplied"
            )
        if record is not None:
            record(decision)
        return decision
