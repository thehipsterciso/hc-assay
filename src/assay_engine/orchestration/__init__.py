"""Orchestration & governance gates — the analysis graph and its human-in-the-loop gates.

The phase machine advances a study through its structural transitions; deterministic,
code-enforced gates sit at those transitions and cannot be silently bypassed (GOVERNANCE.md).
The graph itself is built on LangGraph/LangChain and lifted from the prior platform.
"""

from assay_engine.orchestration.gates import Gate, GateDecision, GateError
from assay_engine.orchestration.phases import Phase

__all__ = ["Gate", "GateDecision", "GateError", "Phase"]
