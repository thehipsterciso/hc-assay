"""Human-in-the-loop gate node — the interrupt/resume protocol (GOVERNANCE.md).

:func:`make_gate_node` turns an engine :class:`~assay_engine.orchestration.gates.Gate` plus a
proposal builder into a LangGraph node that pauses the run at the gate (``interrupt``),
surfaces a proposal to the operator, and on resume validates and records the decision.

The **gate-correlation guard** rejects a resumed decision aimed at a *different* gate than the
one currently parked — a stale or misrouted decision (e.g. delivered late through the
governance channel) must not be applied to whatever gate happens to be waiting. The guard's
expected gate is the gate the operator named in the resume value, compared against this node's
gate; auto-deriving it from the parked gate would make the guard always match and thus a no-op.

The node returns a partial state update appending one record to ``gate_decisions``; a study's
graph state should declare ``gate_decisions`` with a list/add reducer so records accumulate
across gates. The decision/recording logic (:func:`apply_gate_decision`) is pure and tested
offline; only the ``interrupt`` call requires LangGraph (the optional ``orchestration`` extra,
imported lazily).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from assay_engine.orchestration.gates import Gate, GateError

GateProposal = Callable[[Mapping[str, Any]], Mapping[str, Any]]

_VALID_DECISIONS = frozenset({"approved", "rejected", "deferred"})


def apply_gate_decision(gate: Gate, resumed: Any) -> dict[str, Any]:
    """Validate a resumed operator decision and return the state update to record it.

    Raises :class:`GateError` if the resume value is malformed, targets a different gate
    (correlation guard), or carries an unrecognized decision.
    """
    if not isinstance(resumed, Mapping):
        raise GateError(
            f"gate {gate.name!r}: resume value must be a mapping, got {type(resumed).__name__}"
        )
    target = resumed.get("gate_id")
    if target != gate.name:
        raise GateError(
            f"gate {gate.name!r}: resumed decision targets {target!r} — stale or misrouted; "
            "rejecting (gate-correlation guard)"
        )
    decision = str(resumed.get("decision", "")).strip().lower()
    if decision not in _VALID_DECISIONS:
        raise GateError(
            f"gate {gate.name!r}: invalid decision {decision!r} "
            f"(expected one of {sorted(_VALID_DECISIONS)})"
        )
    record = {
        "gate": gate.name,
        "decision": decision,
        "rationale": str(resumed.get("rationale", "")),
    }
    return {"gate_decisions": [record]}


def make_gate_node(gate: Gate, propose: GateProposal) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build a LangGraph node that parks at ``gate`` for an operator decision.

    ``propose(state)`` returns the proposal payload surfaced to the operator (what the gate is
    asking them to approve). The node returns a ``{"gate_decisions": [record]}`` update.
    """

    def node(state: Mapping[str, Any]) -> dict[str, Any]:
        try:
            from langgraph.types import interrupt
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RuntimeError(
                "orchestration requires the 'orchestration' extra (langgraph) — not installed"
            ) from exc
        proposal = propose(state)
        resumed = interrupt({"gate_id": gate.name, "proposal": dict(proposal)})
        return apply_gate_decision(gate, resumed)

    return node
