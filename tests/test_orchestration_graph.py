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
        lambda ctx: __import__(
            "assay_engine.orchestration.gates", fromlist=["GateDecision"]
        ).GateDecision(approved=True, gate="gate_2", reason="ok"),
    )


# ---- apply_gate_decision (pure) ----


def test_apply_gate_decision_records_valid():
    upd = apply_gate_decision(
        _gate(), {"gate_id": "gate_2", "decision": "Approved", "rationale": "looks good"}
    )
    assert upd == {
        "gate_decisions": [{"gate": "gate_2", "decision": "approved", "rationale": "looks good"}]
    }


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
    captured: dict = {"payloads": [], "resumes": []}

    def fake_interrupt(payload):
        captured["payloads"].append(payload)
        if not captured["resumes"]:
            raise AssertionError("interrupt called more times than resumes provided")
        return captured["resumes"].pop(0)

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


def test_make_gate_node_warns_when_no_recorder():
    # #F-007: building a gate node without a recorder is a GOVERNANCE §3 audit gap (decisions
    # live only in non-tamper-evident graph state). The insecure config must warn, not pass
    # silently.
    with pytest.warns(UserWarning, match="audit gap"):
        make_gate_node(_gate(), lambda state: {})


def test_make_gate_node_with_recorder_does_not_warn(recwarn):
    make_gate_node(_gate(), lambda state: {}, recorder=lambda r: None)
    assert not [w for w in recwarn.list if "audit gap" in str(w.message)]


def test_gate_node_interrupts_with_proposal_and_records(fake_langgraph):
    fake_langgraph["resumes"] = [{"gate_id": "gate_2", "decision": "approved", "rationale": "ok"}]
    node = make_gate_node(_gate(), lambda state: {"hypotheses": state.get("n", 0)})
    upd = node({"n": 3})
    assert fake_langgraph["payloads"][0] == {"gate_id": "gate_2", "proposal": {"hypotheses": 3}}
    assert upd["gate_decisions"][0]["decision"] == "approved"


def test_gate_node_bridges_decision_into_provenance_trail(fake_langgraph):
    # #111: a recorder lands the durable-path gate decision in the hash-chained provenance trail
    from assay_engine.provenance import ProvenanceTrail, verify_records

    trail = ProvenanceTrail()
    fake_langgraph["resumes"] = [{"gate_id": "gate_2", "decision": "approved", "rationale": "ok"}]
    node = make_gate_node(
        _gate(),
        lambda state: {},
        recorder=lambda r: trail.record("gate", f"gate {r['gate']}: {r['decision']}", **r),
    )
    node({})
    verify_records(trail.entries)  # the bridged decision is in an intact hash chain
    gates = [e for e in trail.entries if e.kind == "gate"]
    assert gates and gates[0].payload["decision"] == "approved"


def test_gate_node_reprompts_on_bad_resume_then_recovers(fake_langgraph):
    # issue #G1: a mis-correlated then malformed resume must re-fire interrupt, not raise/brick
    fake_langgraph["resumes"] = [
        {"gate_id": "gate_9", "decision": "approved"},  # wrong gate -> re-prompt
        {"gate_id": "gate_2", "decision": "huh"},  # invalid decision -> re-prompt
        {"gate_id": "gate_2", "decision": "approved", "rationale": "ok"},  # good
    ]
    node = make_gate_node(_gate(), lambda state: {})
    upd = node({})
    assert upd["gate_decisions"][0]["decision"] == "approved"
    assert len(fake_langgraph["payloads"]) == 3
    assert "error" in fake_langgraph["payloads"][1]  # re-prompt carried the correlation error
    assert "error" in fake_langgraph["payloads"][2]  # and the invalid-decision error


def test_gate_node_noop_when_already_approved(fake_langgraph):
    # issue #G2: re-entering an approved gate is a no-op (no interrupt, no duplicate record)
    fake_langgraph["resumes"] = []  # interrupt must NOT be called
    node = make_gate_node(_gate(), lambda state: {})
    upd = node({"gate_decisions": [{"gate": "gate_2", "decision": "approved", "rationale": "x"}]})
    assert upd == {}
    assert fake_langgraph["payloads"] == []


def test_gate_node_reprompts_when_previously_rejected(fake_langgraph):
    # rejected is NOT terminal — the gate must re-prompt so a revise->re-review loop works
    fake_langgraph["resumes"] = [
        {"gate_id": "gate_2", "decision": "approved", "rationale": "now ok"}
    ]
    node = make_gate_node(_gate(), lambda state: {})
    upd = node({"gate_decisions": [{"gate": "gate_2", "decision": "rejected", "rationale": "no"}]})
    assert upd["gate_decisions"][0]["decision"] == "approved"
    assert len(fake_langgraph["payloads"]) == 1


@pytest.mark.parametrize("rationale", [None, "", "   ", "\t\n"])
def test_blank_rationale_defaults_to_sentinel(rationale):
    payload = {"gate_id": "gate_2", "decision": "rejected"}
    if rationale is not None:
        payload["rationale"] = rationale
    upd = apply_gate_decision(_gate(), payload)
    assert upd["gate_decisions"][0]["rationale"] == "No rationale provided."


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


def test_compile_graph_requires_checkpointer_for_gate_graph():
    # issue #G3: a gate-bearing graph without a checkpointer would never park — fail loud
    with pytest.raises(RuntimeError, match="checkpointer"):
        compile_graph(dict, build=lambda b: None, checkpointer=None, requires_checkpointer=True)


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def invoke(self, arg, config=None, durability=None):
        self.calls.append((arg, config, durability))
        return {"ok": True}


def test_run_wires_thread_id_and_recursion_limit():
    g = _FakeGraph()
    run(g, {"x": 1}, run_id="run-7", trace=False)
    arg, config, durability = g.calls[0]
    assert arg == {"x": 1}
    assert config["configurable"]["thread_id"] == "run-7"
    assert config["recursion_limit"] == RECURSION_LIMIT
    assert "checkpoint_id" not in config["configurable"]  # resume!=replay (no time-travel id)
    assert durability == "sync"  # parked-gate state persisted before the operator is notified


def test_resume_sends_command_with_decision(fake_langgraph):
    g = _FakeGraph()
    resume(g, run_id="run-7", gate_id="gate_2", decision="approved", rationale="ok", trace=False)
    arg, config, durability = g.calls[0]
    assert isinstance(arg, sys.modules["langgraph.types"].Command)
    assert arg.resume == {"gate_id": "gate_2", "decision": "approved", "rationale": "ok"}
    assert config["configurable"]["thread_id"] == "run-7"
    assert "checkpoint_id" not in config["configurable"]
    assert durability == "sync"
