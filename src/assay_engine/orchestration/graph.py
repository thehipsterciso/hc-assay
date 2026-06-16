"""Analysis-graph assembly + run/resume — the goal-agnostic orchestration wiring.

The concrete nodes and topology of a study's analysis graph are the study's (adapter's)
responsibility — they encode dataset specifics and so must not live in the engine (ADR-0002).
The engine provides the reusable, hardened mechanics around them:

- compile a LangGraph ``StateGraph`` with the durable checkpointer attached (so a run can
  interrupt at a gate and resume later);
- bound non-converging gate-rejection loops with a recursion limit, so a run that never
  converges fails loud (``GraphRecursionError``) instead of looping unbounded;
- stamp ``run_id`` as the checkpointer ``thread_id`` and onto traces (cross-store
  correlation), inside a trace context;
- the gate interrupt/resume protocol with its correlation guard (see
  :mod:`assay_engine.orchestration.gatenode`).

LangGraph is an optional extra (``orchestration``, ADR-0006), imported lazily.
"""

from __future__ import annotations

from typing import Any, Callable

from assay_engine.observability.tracing import bootstrap_tracing, run_trace_context

# Upper bound on graph super-steps per run. Bounds a gate-rejection→re-analysis loop so a
# non-converging run terminates loudly instead of hanging.
RECURSION_LIMIT = 50


def _require_langgraph() -> Any:
    try:
        import langgraph  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "orchestration requires the 'orchestration' extra (langgraph) — not installed"
        ) from exc
    return langgraph


def compile_graph(
    state_schema: Any,
    *,
    build: Callable[[Any], None],
    checkpointer: Any | None = None,
    requires_checkpointer: bool = False,
) -> Any:
    """Compile a study's analysis graph.

    ``build(builder)`` is a study-supplied callback that adds the study's nodes, edges, and
    entry point to the LangGraph ``StateGraph`` builder; the engine owns construction and
    attaching the durable ``checkpointer``. Returns the compiled graph.

    Set ``requires_checkpointer=True`` for any graph containing gate nodes: ``interrupt`` is a
    silent no-op without a checkpointer, so a gate graph compiled without one would never park
    for the operator. The engine fails loud rather than ship a silently-broken governance
    graph (audit #G3). The engine cannot introspect the study-supplied ``build`` callback for
    gate nodes, so this is the caller's responsibility: **any study wiring**
    :func:`~assay_engine.orchestration.gatenode.make_gate_node` **must pass
    ``requires_checkpointer=True``** (see GOVERNANCE.md "Gate interrupt/resume protocol").
    """
    if requires_checkpointer and checkpointer is None:
        raise RuntimeError(
            "compile_graph(requires_checkpointer=True): a gate-bearing graph needs a durable "
            "checkpointer — interrupt() cannot park the run for the operator without one"
        )
    _require_langgraph()
    from langgraph.graph import StateGraph

    builder = StateGraph(state_schema)
    build(builder)
    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


def _thread_config(run_id: str, recursion_limit: int) -> dict[str, Any]:
    # Resume/run are keyed ONLY by thread_id — the checkpointer loads the latest (interrupted)
    # state itself. We deliberately do NOT thread a checkpoint_id: passing one is the
    # time-travel/replay API, and Command(resume=...) WITH a checkpoint_id replays from that
    # historical checkpoint instead of resuming the interrupt (version-dependent; LangGraph
    # issue #7361) — which would re-execute already-completed gates and break governance order.
    return {
        "configurable": {"thread_id": run_id},
        "recursion_limit": recursion_limit,
    }


def run(
    graph: Any,
    state: Any,
    *,
    run_id: str,
    recursion_limit: int = RECURSION_LIMIT,
    trace: bool = True,
) -> Any:
    """Invoke a compiled graph for ``run_id`` (the checkpointer thread id), within a trace
    context, bounded by ``recursion_limit``. The run parks at the first gate ``interrupt``;
    resume it with :func:`resume`.

    Uses ``durability="sync"``: a governance run must have its parked-at-gate checkpoint written
    *before* the operator is notified, so a crash in the (otherwise async) write window cannot
    lose the interrupt. (The LangGraph default is ``"async"``.)
    """
    if trace:
        bootstrap_tracing()
    config = _thread_config(run_id, recursion_limit)
    with run_trace_context(run_id):
        return graph.invoke(state, config=config, durability="sync")


def resume(
    graph: Any,
    *,
    run_id: str,
    gate_id: str,
    decision: str,
    rationale: str,
    recursion_limit: int = RECURSION_LIMIT,
    trace: bool = True,
) -> Any:
    """Resume a run parked at a gate with the operator's decision.

    ``gate_id`` is the gate the operator intended to decide (from the governance channel) and
    is REQUIRED — the gate node's correlation guard rejects it if it does not match the parked
    gate, so a stale/misrouted decision cannot resume the wrong gate. Must use the SAME
    checkpointer the run started with (``thread_id == run_id``); resume always continues the
    latest interrupted state for the thread (no checkpoint_id — see :func:`_thread_config`).
    """
    _require_langgraph()
    from langgraph.types import Command

    if trace:
        bootstrap_tracing()
    config = _thread_config(run_id, recursion_limit)
    resume_value = {"gate_id": gate_id, "decision": decision, "rationale": rationale}
    with run_trace_context(run_id):
        return graph.invoke(Command(resume=resume_value), config=config, durability="sync")
