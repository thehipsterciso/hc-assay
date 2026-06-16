"""Human-in-the-loop gate node — the interrupt/resume protocol (GOVERNANCE.md).

:func:`make_gate_node` turns an engine :class:`~assay_engine.orchestration.gates.Gate` plus a
proposal builder into a LangGraph node that pauses the run at the gate (``interrupt``),
surfaces a proposal to the operator, and on resume validates and records the decision.

The **gate-correlation guard** rejects a resumed decision aimed at a *different* gate than the
one currently parked — a stale or misrouted decision (e.g. delivered late through the
governance channel) must not be applied to whatever gate happens to be waiting. The guard's
expected gate is the gate the operator named in the resume value, compared against this node's
gate; auto-deriving it from the parked gate would make the guard always match and thus a no-op.

Two further hardened behaviors, ported faithfully from the prior platform's gate node:

- **Re-prompt on a bad resume (not raise).** ``interrupt()`` consumes and *persists* the
  resume value into the checkpoint *before* the node returns, so raising on a malformed or
  mis-correlated value would strand it in the checkpoint and replay it forever — the gate
  would be permanently bricked. Instead the node validates inside a loop and re-fires
  ``interrupt()`` (carrying the error) on a bad value, so the operator can re-submit and
  actually recover.
- **Terminal-decision idempotency.** An ``approved`` decision is terminal: re-entering an
  already-approved gate is a no-op (it does not re-prompt or re-record). ``rejected`` and
  ``deferred`` are deliberately NOT terminal, so a reject→revise→re-review loop re-fires the
  interrupt as intended.

The node returns a partial state update appending one record to ``gate_decisions``; a study's
graph state should declare ``gate_decisions`` with a list/add reducer so records accumulate
across gates. The decision/recording validator (:func:`apply_gate_decision`) is pure and
tested offline; only the ``interrupt`` call requires LangGraph (the optional ``orchestration``
extra, imported lazily).
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
    # A rejection/deferral with no rationale is governance-relevant; record a sentinel
    # rather than an empty string so the audit trail is never silently blank.
    rationale = str(resumed.get("rationale") or "No rationale provided.")
    record = {"gate": gate.name, "decision": decision, "rationale": rationale}
    return {"gate_decisions": [record]}


# Only an approval is terminal: a re-entered approved gate is a no-op, but a rejected/deferred
# gate must re-fire its interrupt so a revise→re-review loop can re-prompt the operator.
_TERMINAL_DECISIONS = frozenset({"approved"})


def already_decided(state: Mapping[str, Any], gate_name: str) -> bool:
    """True if ``gate_name`` already holds a terminal (approved) decision in ``gate_decisions``."""
    for record in state.get("gate_decisions", []) or []:
        if record.get("gate") == gate_name and record.get("decision") in _TERMINAL_DECISIONS:
            return True
    return False


def make_gate_node(gate: Gate, propose: GateProposal) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build a LangGraph node that parks at ``gate`` for an operator decision.

    ``propose(state)`` returns the proposal payload surfaced to the operator (what the gate is
    asking them to approve). The node returns a ``{"gate_decisions": [record]}`` update, or
    ``{}`` (no-op) if the gate is already terminally approved.
    """

    def node(state: Mapping[str, Any]) -> dict[str, Any]:
        if already_decided(state, gate.name):
            return {}  # terminal decision exists — do not re-prompt or re-record
        try:
            from langgraph.types import interrupt
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RuntimeError(
                "orchestration requires the 'orchestration' extra (langgraph) — not installed"
            ) from exc
        proposal = dict(propose(state))
        current: dict[str, Any] = {"gate_id": gate.name, "proposal": proposal}
        # Validate inside a loop: on a bad/mis-correlated resume, re-fire interrupt (next
        # resume index) carrying the error rather than raising — a raise would strand the
        # bad value in the checkpoint and replay it forever, bricking the gate.
        while True:
            resumed = interrupt(current)
            try:
                return apply_gate_decision(gate, resumed)
            except GateError as exc:
                current = {"gate_id": gate.name, "proposal": proposal, "error": str(exc)}

    return node
