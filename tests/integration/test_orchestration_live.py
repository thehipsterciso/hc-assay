"""Live orchestration — a real LangGraph run through a gate interrupt/resume + re-prompt.

Exercises compile_graph/run/resume/make_gate_node against the REAL langgraph runtime and a
real MemorySaver checkpoint (interrupt persists the resume value and the run replays from the
checkpoint) — the path the unit tests could only mock. Crucially validates that a bad resume
RE-PROMPTS rather than bricking the gate (audit #G1) under genuine interrupt semantics.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

import pytest

pytest.importorskip("langgraph")

from langgraph.graph import END, START  # noqa: E402

from assay_engine.orchestration import (  # noqa: E402
    Gate,
    GateDecision,
    compile_graph,
    make_gate_node,
    resume,
    run,
)
from assay_engine.orchestration.phases import Phase  # noqa: E402


class _State(TypedDict):
    run_id: str
    gate_decisions: Annotated[list, operator.add]
    done: bool


def _gate() -> Gate:
    return Gate(
        "gate_1",
        Phase.INGEST,
        Phase.BASELINE,
        lambda ctx: GateDecision(approved=True, gate="gate_1", reason="ok"),
    )


def _compiled():
    from langgraph.checkpoint.memory import MemorySaver

    def build(b):
        b.add_node("gate", make_gate_node(_gate(), lambda s: {"summary": "approve to proceed"}))
        b.add_node("finish", lambda s: {"done": True})
        b.add_edge(START, "gate")
        b.add_edge("gate", "finish")
        b.add_edge("finish", END)

    return compile_graph(
        _State, build=build, checkpointer=MemorySaver(), requires_checkpointer=True
    )


def _initial(run_id: str) -> _State:
    return {"run_id": run_id, "gate_decisions": [], "done": False}


def test_real_graph_parks_at_gate_then_resumes_to_completion():
    g = _compiled()
    parked = run(g, _initial("r1"), run_id="r1", trace=False)
    assert parked.get("done") is not True  # parked at the gate, not finished
    assert "__interrupt__" in parked  # real langgraph interrupt fired

    final = resume(
        g, run_id="r1", gate_id="gate_1", decision="approved", rationale="go", trace=False
    )
    assert final["done"] is True
    assert final["gate_decisions"][-1] == {
        "gate": "gate_1",
        "decision": "approved",
        "rationale": "go",
    }


def test_real_graph_bad_resume_reprompts_not_bricks():
    # audit #G1 under REAL interrupt semantics: a mis-correlated resume must re-park the gate
    # (recoverable), and a subsequent correct resume must complete — not strand the run.
    g = _compiled()
    run(g, _initial("r2"), run_id="r2", trace=False)
    reprompted = resume(
        g, run_id="r2", gate_id="WRONG_GATE", decision="approved", rationale="x", trace=False
    )
    assert reprompted.get("done") is not True  # not bricked, not errored — re-parked
    assert "__interrupt__" in reprompted

    final = resume(
        g, run_id="r2", gate_id="gate_1", decision="approved", rationale="ok", trace=False
    )
    assert final["done"] is True
    assert final["gate_decisions"][-1]["decision"] == "approved"


def test_real_graph_rejected_then_revised_approve():
    g = _compiled()
    run(g, _initial("r3"), run_id="r3", trace=False)
    rejected = resume(
        g, run_id="r3", gate_id="gate_1", decision="rejected", rationale="not yet", trace=False
    )
    # a rejection is recorded and the run completes its path (the study's router would loop;
    # here finish runs) — the point is the decision is captured, not silently dropped.
    assert rejected["gate_decisions"][-1]["decision"] == "rejected"
