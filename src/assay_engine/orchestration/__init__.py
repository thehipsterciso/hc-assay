"""Orchestration & governance gates — the analysis graph and its human-in-the-loop gates.

The phase machine advances a study through its structural transitions; deterministic,
code-enforced gates sit at those transitions and cannot be silently bypassed (GOVERNANCE.md).
The graph itself is built on LangGraph/LangChain and lifted from the prior platform.
"""

from assay_engine.orchestration.gatenode import (
    GateProposal,
    already_decided,
    apply_gate_decision,
    make_gate_node,
)
from assay_engine.orchestration.gates import ALL_MODES, Gate, GateDecision, GateError
from assay_engine.orchestration.graph import (
    RECURSION_LIMIT,
    compile_graph,
    resume,
    run,
)
from assay_engine.orchestration.phases import (
    Phase,
    legal_transition,
    required_phases,
)

__all__ = [
    "Gate",
    "GateDecision",
    "GateError",
    "ALL_MODES",
    "Phase",
    "legal_transition",
    "required_phases",
    "GateProposal",
    "apply_gate_decision",
    "already_decided",
    "make_gate_node",
    "RECURSION_LIMIT",
    "compile_graph",
    "run",
    "resume",
]
