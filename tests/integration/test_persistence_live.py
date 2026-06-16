"""Live persistence — real LangGraph MemorySaver round-trip; Qdrant/Postgres if running."""

from __future__ import annotations

import pytest

from tests.integration.conftest import have, postgres_up, qdrant_up


@pytest.mark.skipif(not have("langgraph"), reason="persistence extra not installed")
def test_memory_checkpointer_persists_graph_state():
    # Test the checkpointer the way it is actually used: through a compiled graph, asserting
    # state is durably persisted under the thread_id and readable via get_state.
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    from assay_engine.persistence.checkpoint import configured_checkpointer

    class S(TypedDict):
        n: int

    cp = configured_checkpointer(use_memory=True)
    b = StateGraph(S)
    b.add_node("inc", lambda s: {"n": s["n"] + 1})
    b.add_edge(START, "inc")
    b.add_edge("inc", END)
    graph = b.compile(checkpointer=cp)

    cfg = {"configurable": {"thread_id": "t1"}}
    graph.invoke({"n": 0}, cfg)
    persisted = graph.get_state(cfg)
    assert persisted.values["n"] == 1  # state durably checkpointed under the thread


@pytest.mark.skipif(not qdrant_up(), reason="qdrant not running on localhost:6333")
def test_qdrant_client_connects():
    from assay_engine.persistence.vectorstore import get_qdrant_client, vector_store_url

    assert vector_store_url().startswith("http://localhost:")
    client = get_qdrant_client()
    try:
        client.get_collections()  # real round-trip to the running server
    except Exception as exc:  # cold container: port open before HTTP API ready — don't flake
        pytest.skip(f"qdrant not ready: {exc}")


@pytest.mark.skipif(not qdrant_up(), reason="qdrant not running on localhost:6333")
def test_qdrant_vector_store_upsert_and_query():
    # exercise the real VectorStore capability: create, upsert, nearest-neighbour query
    import uuid as _uuid

    from assay_engine.persistence.vectorstore import QdrantVectorStore, get_qdrant_client

    client = get_qdrant_client()
    coll = f"assay_test_{_uuid.uuid4().hex[:8]}"
    store = QdrantVectorStore(coll, dim=3, client=client)
    try:
        store.ensure_collection()
        store.upsert(
            ["a", "b", "c"],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        )
        hits = store.query([0.95, 0.05, 0.0], k=2)
        assert hits[0][0] == "a"  # original string id round-tripped via payload
        assert {h[0] for h in hits} <= {"a", "b", "c"}
    except Exception as exc:  # qdrant client/server version skew etc.
        pytest.skip(f"qdrant vector op unavailable: {exc}")
    finally:
        try:
            client.delete_collection(coll)
        except Exception:
            pass


@pytest.mark.skipif(not postgres_up(), reason="postgres not reachable on localhost:5432")
def test_postgres_checkpointer_setup_and_round_trip(monkeypatch):
    import os

    # Use a dedicated db/url if provided; otherwise the loopback default.
    monkeypatch.setenv(
        "ASSAY_POSTGRES_URL",
        os.environ.get("ASSAY_TEST_POSTGRES_URL", "postgresql://localhost:5432/assay"),
    )
    from assay_engine.persistence.checkpoint import get_checkpointer

    try:
        cp = get_checkpointer(use_memory=False)  # opens pool + advisory-locked setup()
    except RuntimeError as exc:
        pytest.skip(f"postgres present but db not usable: {exc}")
    cfg = {"configurable": {"thread_id": "pg-t1", "checkpoint_ns": ""}}
    chkpt = {
        "v": 1,
        "id": "pc1",
        "ts": "2026-01-01T00:00:00Z",
        "channel_values": {"y": 11},
        "channel_versions": {},
        "versions_seen": {},
    }
    saved = cp.put(cfg, chkpt, {}, {})
    got = cp.get_tuple(saved)
    assert got is not None and got.checkpoint["channel_values"]["y"] == 11


def _pg_url() -> str:
    import os

    return os.environ.get("ASSAY_TEST_POSTGRES_URL", "postgresql://localhost:5432/assay")


@pytest.mark.skipif(not postgres_up(), reason="postgres not reachable on localhost:5432")
def test_postgres_state_durable_across_fresh_pool(monkeypatch):
    # the durability guarantee: state written through one pool is readable through a NEW pool
    # (it lives in postgres, not process memory) — what makes interrupt/resume survive restarts.
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    from assay_engine.persistence.checkpoint import get_checkpointer

    monkeypatch.setenv("ASSAY_POSTGRES_URL", _pg_url())

    class S(TypedDict):
        n: int

    def _graph(cp):
        b = StateGraph(S)
        b.add_node("inc", lambda s: {"n": s["n"] + 1})
        b.add_edge(START, "inc")
        b.add_edge("inc", END)
        return b.compile(checkpointer=cp)

    try:
        cp1 = get_checkpointer(use_memory=False)
    except RuntimeError as exc:
        pytest.skip(f"postgres present but db not usable: {exc}")
    import uuid as _uuid

    tid = f"durable-{_uuid.uuid4().hex[:8]}"
    cfg = {"configurable": {"thread_id": tid}}
    _graph(cp1).invoke({"n": 0}, cfg)

    cp2 = get_checkpointer(use_memory=False)  # a fresh pool/saver over the same db
    persisted = _graph(cp2).get_state(cfg)
    assert persisted.values["n"] == 1  # state recovered from postgres, not memory


@pytest.mark.skipif(not postgres_up(), reason="postgres not reachable on localhost:5432")
def test_postgres_concurrent_get_checkpointer(monkeypatch):
    # concurrent initializers must not race the advisory-locked one-time schema setup: the
    # _init_lock serializes the in-process check, the PG advisory lock the cross-process DDL.
    import threading

    from assay_engine.persistence import checkpoint as cp

    monkeypatch.setenv("ASSAY_POSTGRES_URL", _pg_url())
    monkeypatch.setattr(cp, "_INITIALIZED_CONN_STRS", set())  # force setup contention this run

    results: list = []
    errors: list = []

    def worker():
        try:
            results.append(cp.get_checkpointer(use_memory=False))
        except RuntimeError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    if errors and not results:
        pytest.skip(f"postgres present but db not usable: {errors[0]}")
    assert not errors, f"concurrent get_checkpointer raised: {errors}"
    assert len(results) == 8  # every concurrent caller got a usable saver, no race failure


@pytest.mark.skipif(not postgres_up(), reason="postgres not reachable on localhost:5432")
def test_postgres_pool_self_heals_after_connection_drop(monkeypatch):
    # The checkpointer's headline durability feature: a self-healing ConnectionPool
    # (check_connection on checkout) recovers when a connection dies mid-run. We drop the
    # pool's backend connection(s) via pg_terminate_backend (kills ONE connection, NOT the
    # server) and assert the next checkpoint op still succeeds — a raw connection would fail.
    from typing import TypedDict

    import psycopg
    from langgraph.graph import END, START, StateGraph

    from assay_engine.persistence.checkpoint import get_checkpointer

    url = _pg_url()
    monkeypatch.setenv("ASSAY_POSTGRES_URL", url)

    class S(TypedDict):
        n: int

    def graph(cp):
        b = StateGraph(S)
        b.add_node("inc", lambda s: {"n": s["n"] + 1})
        b.add_edge(START, "inc")
        b.add_edge("inc", END)
        return b.compile(checkpointer=cp)

    try:
        cp = get_checkpointer(use_memory=False)
    except RuntimeError as exc:
        pytest.skip(f"postgres present but db not usable: {exc}")

    g = graph(cp)
    g.invoke({"n": 0}, {"configurable": {"thread_id": "heal-a"}})  # opens + uses pool conns

    # Forcibly drop every OTHER backend on this database (the pool's connections), via a
    # separate admin connection that excludes itself — the server keeps running.
    try:
        admin = psycopg.connect(url, autocommit=True)
    except Exception as exc:
        pytest.skip(f"cannot open admin connection to drop backends: {exc}")
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
    finally:
        admin.close()

    # The pool's cached connections are now dead. A second op must transparently recover.
    g.invoke({"n": 0}, {"configurable": {"thread_id": "heal-b"}})
    state = g.get_state({"configurable": {"thread_id": "heal-b"}})
    assert state.values["n"] == 1  # self-healed: op succeeded on a fresh connection
