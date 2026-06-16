"""Orchestration graph wiring + gate-node interrupt/resume protocol (offline, langgraph mocked)."""

import sys
import types

import pytest

from assay_engine.orchestration.gatenode import apply_gate_decision, make_gate_node
from assay_engine.orchestration.gates import Gate, GateError
from assay_engine.orchestration.graph import RECURSION_LIMIT, compile_graph, resume, run
from assay_engine.orchestration.phases import Phase


def _gate() -> Gate:
    return Gate(
        "gate_2",
        Phase.PREREGISTER,
        Phase.CONFIRM,
        lambda ctx: __import__("assay_engine.orchestration.gates", fromlist=["GateDecision"]).GateDecision(
            approved=True, gate="gate_2", reason="ok"
        ),
    )


# ---- apply_gate_decision (pure) ----

def test_apply_gate_decision_records_valid():
    upd = apply_gate_decision(_gate(), {"gate_id": "gate_2", "decision": "Approved", "rationale": "looks good"})
    assert upd == {"gate_decisions": [{"gate": "gate_2", "decision": "approved", "rationale": "looks good"}]}


def test_apply_gate_decision_correlation_guard_rejects_other_gate():
    with pytest.raises(GateError, match="correlation guard"):
        apply_gate_decision(_gate(), {"gate_id": "gate_5", "decision": "approved"})


def test_apply_gate_decision_rejects_non_mapping():
    with pytest.raises(GateError):
        apply_gate_decision(_gate(), "approved")


def test_apply_gate_decision_rejects_unknown_decision():
    with pytest.raises(GateError, match="invalid decision"):
        apply_gate_decision(_gate(), {"gate_id": "gate_2", "decision": "maybe"})


@pytest.mark.parametrize("d", ["approved", "rejected", "deferred"])
def test_apply_gate_decision_accepts_all_verdicts(d):
    upd = apply_gate_decision(_gate(), {"gate_id": "gate_2", "decision": d})
    assert upd["gate_decisions"][0]["decision"] == d


# ---- fake langgraph injection ----

@pytest.fixture
def fake_langgraph(monkeypatch):
    captured: dict = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        return captured["resume"]

    class Command:
        def __init__(self, resume=None):
            self.resume = resume

    class StateGraph:
        def __init__(self, schema):
            captured["schema"] = schema
            self.nodes = []

        def add_node(self, name, fn):
            self.nodes.append(name)

        def compile(self, **kw):
            captured["compile_kw"] = kw
            return ("compiled", tuple(self.nodes))

    lg = types.ModuleType("langgraph")
    types_mod = types.ModuleType("langgraph.types")
    types_mod.interrupt = fake_interrupt
    types_mod.Command = Command
    graph_mod = types.ModuleType("langgraph.graph")
    graph_mod.StateGraph = StateGraph
    monkeypatch.setitem(sys.modules, "langgraph", lg)
    monkeypatch.setitem(sys.modules, "langgraph.types", types_mod)
    monkeypatch.setitem(sys.modules, "langgraph.graph", graph_mod)
    return captured


# ---- make_gate_node ----

def test_gate_node_interrupts_with_proposal_and_records(fake_langgraph):
    fake_langgraph["resume"] = {"gate_id": "gate_2", "decision": "approved", "rationale": "ok"}
    node = make_gate_node(_gate(), lambda state: {"hypotheses": state.get("n", 0)})
    upd = node({"n": 3})
    assert fake_langgraph["payload"] == {"gate_id": "gate_2", "proposal": {"hypotheses": 3}}
    assert upd["gate_decisions"][0]["decision"] == "approved"


def test_gate_node_correlation_guard_on_resume(fake_langgraph):
    fake_langgraph["resume"] = {"gate_id": "gate_9", "decision": "approved"}
    node = make_gate_node(_gate(), lambda state: {})
    with pytest.raises(GateError, match="correlation guard"):
        node({})


# ---- compile_graph / run / resume ----

def test_compile_graph_invokes_build_and_attaches_checkpointer(fake_langgraph):
    built = {}
    cp = object()

    def build(b):
        built["called"] = True
        b.add_node("n", lambda s: s)

    graph = compile_graph(dict, build=build, checkpointer=cp)
    assert built["called"] is True
    assert fake_langgraph["compile_kw"] == {"checkpointer": cp}
    assert graph == ("compiled", ("n",))


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def invoke(self, arg, config=None):
        self.calls.append((arg, config))
        return {"ok": True}


def test_run_wires_thread_id_and_recursion_limit():
    g = _FakeGraph()
    run(g, {"x": 1}, run_id="run-7", trace=False)
    arg, config = g.calls[0]
    assert arg == {"x": 1}
    assert config["configurable"]["thread_id"] == "run-7"
    assert config["recursion_limit"] == RECURSION_LIMIT


def test_resume_sends_command_with_decision(fake_langgraph):
    g = _FakeGraph()
    resume(g, run_id="run-7", gate_id="gate_2", decision="approved", rationale="ok", trace=False)
    arg, config = g.calls[0]
    assert isinstance(arg, sys.modules["langgraph.types"].Command)
    assert arg.resume == {"gate_id": "gate_2", "decision": "approved", "rationale": "ok"}
    assert config["configurable"]["thread_id"] == "run-7"
