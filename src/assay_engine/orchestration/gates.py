"""Governance gates — deterministic, code-enforced transition checks.

A gate guards a transition between phases. It evaluates code-enforced preconditions (the
firewalls, lock state) and, where the governance model requires it, a recorded human
approval. A gate cannot be silently bypassed: a transition is legal only if the gate returns
an ``approved`` decision, and a ``requires_human`` gate refuses to pass unless a provenance
recorder is supplied to capture the decision (audit pass 1, issue #11).

Two complementary gate mechanisms exist (ADR-0010):

- This ``Gate``/``evaluate`` model is the **declarative precondition check** — mode-aware
  transition legality (issue #9) plus a fail-loud human-approval hook that refuses to pass a
  ``requires_human`` gate without a :class:`~assay_engine.provenance.ProvenanceTrail`-backed
  recorder. It is used by a study that builds its own LangGraph topology with
  :func:`~assay_engine.orchestration.gatenode.make_gate_node` for durable interrupt/resume.
- The composed runner :func:`assay_engine.pipeline.run_study` uses the *synchronous*
  ``GateReview``/``GateHandler`` model for in-process governance (a handler may approve, block,
  or be wired to park). Both record every decision to the append-only provenance trail, which
  **is** now wired (:mod:`assay_engine.provenance`) — the present-tense guarantees in
  GOVERNANCE.md hold. Use the graph mechanism when you need cross-process durable parking; use
  the runner handler for a straight-line governed run.
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
        study_modes: frozenset[StudyMode] | None = None,
        record: ProvenanceRecorder | None = None,
    ) -> GateDecision:
        # The gate's own `modes` is a self-declaration. When the orchestration layer supplies
        # the running study's actual modes, the transition must be legal under THOSE modes —
        # so a discovery-only run cannot pass a CONFIRM->ADJUDICATE gate even if the gate
        # over-declares its modes (audit pass 2, issue #23). Fall back to self.modes only
        # until the runner is wired.
        effective_modes = self.modes if study_modes is None else (study_modes & self.modes)
        if not legal_transition(self.frm, self.to, effective_modes):
            raise GateError(
                f"gate {self.name!r} declares an illegal transition for the effective modes: "
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
