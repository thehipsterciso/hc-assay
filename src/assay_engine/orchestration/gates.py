"""Governance gates — deterministic, code-enforced transition checks.

A gate guards a transition between phases. It evaluates code-enforced preconditions (the
firewalls, lock state, provenance recorded) and, where the governance model requires it,
records a human approval. A gate cannot be silently bypassed: the transition is only legal
if the gate returns an ``approved`` decision, and the engine records the decision to the
append-only provenance trail before the next phase runs.

The concrete gate set and the human-in-the-loop wiring are lifted from the prior platform's
governance graph; this module fixes the gate contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from assay_engine.orchestration.phases import Phase


class GateError(RuntimeError):
    """Raised when a transition is attempted through a gate that did not approve it."""


@dataclass(frozen=True, slots=True)
class GateDecision:
    approved: bool
    gate: str
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Gate:
    """A guard on the transition ``frm -> to``.

    ``precondition`` is a pure, code-enforced check over the run context returning a
    :class:`GateDecision`. ``requires_human`` marks gates that additionally need a recorded
    operator approval (handled by the orchestration layer when wired).
    """

    name: str
    frm: Phase
    to: Phase
    precondition: Callable[[Mapping[str, Any]], GateDecision]
    requires_human: bool = False

    def evaluate(self, context: Mapping[str, Any]) -> GateDecision:
        if not self.frm.can_advance_to(self.to):
            raise GateError(
                f"gate {self.name!r} declares an illegal transition "
                f"{self.frm.name} -> {self.to.name}"
            )
        decision = self.precondition(context)
        if not decision.approved:
            raise GateError(f"gate {self.name!r} blocked transition: {decision.reason}")
        return decision
