"""Persistence port — credential redaction, loopback, content-addressing (offline)."""

import importlib.util

import pytest

from assay_engine._local import NonLocalEndpointError
from assay_engine.persistence import vectorstore as vs
from assay_engine.persistence.checkpoint import (
    _sanitize_conn_str,
    configured_checkpointer,
    get_checkpointer,
    get_postgres_connection_string,
    redact_creds,
)
from assay_engine.persistence.vectorstore import get_qdrant_client, vector_store_url
from assay_engine.persistence.versioning import LocalDataVersioner


# ---- credential redaction (security) ----


def test_sanitize_strips_userinfo():
    assert _sanitize_conn_str("postgresql://user:pw@localhost:5432/db") == (
        "postgresql://localhost:5432/db"
    )


def test_sanitize_handles_ipv6():
    out = _sanitize_conn_str("postgresql://u:p@[::1]:5432/db")
    # host re-bracketed, no userinfo
    assert "u:p@" not in out and out == "postgresql://[::1]:5432/db"


@pytest.mark.parametrize("pw", ["plain", "p/w", "p w", "p@ss", "s3cr#t!"])
def test_redact_creds_strips_passwords_with_special_chars(pw):
    conn = f"postgresql://admin:{pw}@localhost:5432/db"
    msg = f"connection failed for {conn} — timeout"
    out = redact_creds(msg, conn)
    assert pw not in out and "admin:" not in out
    assert "localhost:5432/db" in out  # host/port kept for diagnosis


def test_redact_creds_generic_backstop_without_connstr():
    msg = "error at postgresql://u:secret@localhost/db end"
    out = redact_creds(msg)
    assert "secret" not in out and "u:" not in out


# ---- connection string + loopback ----


def test_connection_string_default_is_loopback(monkeypatch):
    monkeypatch.delenv("ASSAY_POSTGRES_URL", raising=False)
    assert "localhost" in get_postgres_connection_string()


def test_connection_string_rejects_remote_env(monkeypatch):
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "postgresql://user:pw@db.example.com:5432/x")
    with pytest.raises(NonLocalEndpointError):
        get_postgres_connection_string()


def test_connection_string_accepts_loopback_env(monkeypatch):
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/x")
    assert get_postgres_connection_string().endswith("/x")


def test_connection_string_rejects_remote_libpq_dsn(monkeypatch):
    # issue #P1: a keyword/value DSN has no '://' and must not bypass loopback enforcement
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "host=db.evil.com port=5432 dbname=x password=s")
    with pytest.raises(NonLocalEndpointError):
        get_postgres_connection_string()


def test_connection_string_accepts_local_libpq_dsn(monkeypatch):
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "host=localhost port=5432 dbname=x")
    assert "localhost" in get_postgres_connection_string()


@pytest.mark.parametrize(
    "dsn",
    [
        "host = db.evil.com dbname=x",  # space around '='
        "host =db.evil.com dbname=x",
        "host= db.evil.com dbname=x",
        "host=  db.evil.com  dbname=x",
        "host\t=\tdb.evil.com dbname=x",  # tabs
        "host='db.evil.com' dbname=x",  # quoted
        "hostaddr=8.8.8.8 dbname=x",
        "HOST=db.evil.com dbname=x",  # case-insensitive key
    ],
)
def test_connection_string_rejects_remote_dsn_all_spellings(monkeypatch, dsn):
    # issue #D1: libpq permits whitespace/quoting around '=' — none may bypass loopback
    monkeypatch.setenv("ASSAY_POSTGRES_URL", dsn)
    with pytest.raises(NonLocalEndpointError):
        get_postgres_connection_string()


def test_connection_string_accepts_local_dsn_with_spaces(monkeypatch):
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "host = 127.0.0.1 dbname = x")
    assert get_postgres_connection_string().startswith("host")


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://localhost/x?host=db.evil.com",  # query host overrides authority
        "postgresql://localhost/x?hostaddr=8.8.8.8",  # libpq dials hostaddr
        "postgresql://localhost/x?host=evil.com&hostaddr=8.8.8.8",
        "postgresql://127.0.0.1/x?host=evil.com",
        "postgresql://[::1]/x?host=evil.com",
        "postgresql://user:pw@localhost:5432/db?host=db.evil.com",
    ],
)
def test_connection_string_rejects_uri_query_host_override(monkeypatch, uri):
    # issue #D2: a URI query host=/hostaddr= overrides the authority host in libpq
    monkeypatch.setenv("ASSAY_POSTGRES_URL", uri)
    with pytest.raises(NonLocalEndpointError):
        get_postgres_connection_string()


def test_connection_string_accepts_uri_with_loopback_query_host(monkeypatch):
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "postgresql://localhost/x?host=127.0.0.1")
    assert get_postgres_connection_string().endswith("?host=127.0.0.1")


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://localhost:5432,evil.com:5432/db",  # multi-host: 2nd is remote (#D3)
        "postgresql://127.0.0.1:5432,8.8.8.8:5432/db",
        "postgresql://localhost:5432,a.evil.com,b.evil.com/db",
        "postgresql://[::1]:5432,evil.com:5432/db",
    ],
)
def test_connection_string_rejects_multihost_with_remote(monkeypatch, uri):
    monkeypatch.setenv("ASSAY_POSTGRES_URL", uri)
    with pytest.raises(NonLocalEndpointError):
        get_postgres_connection_string()


def test_connection_string_accepts_all_loopback_multihost(monkeypatch):
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "postgresql://localhost:5432,127.0.0.1:5433/db")
    assert "127.0.0.1" in get_postgres_connection_string()


@pytest.mark.parametrize(
    "path",
    [r"\\server\share\db.sqlite", "/\\evil\\share", "\\/evil/share", "//evil/share"],
)
def test_require_local_uri_rejects_unc_paths(path):
    from assay_engine._local import require_local_uri

    with pytest.raises(NonLocalEndpointError):
        require_local_uri(path, what="x")


def test_require_local_uri_rejects_backslash_in_authority():
    from assay_engine._local import require_local_uri

    with pytest.raises(NonLocalEndpointError):
        require_local_uri("http://evil.com\\@localhost/x", what="x")


def test_require_local_uri_fails_closed_on_unparseable():
    from assay_engine._local import require_local_uri

    # a malformed IPv6 authority must reject (fail closed), not raise a bare ValueError
    with pytest.raises(NonLocalEndpointError):
        require_local_uri("postgresql://[:::oops]/db", what="x")


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://user@evil.com:5432@localhost/db",  # libpq reads first @ -> host=evil.com
        "postgresql://a@10.0.0.5:5432@localhost/db",
        "postgresql://u:p@93.184.216.34:5432@localhost/db",
        "postgresql://user@evil.com@localhost/db",
    ],
)
def test_connection_string_rejects_userinfo_at_differential(monkeypatch, uri):
    # issue #D5: validator must strip userinfo at the FIRST '@' like libpq, not the last
    monkeypatch.setenv("ASSAY_POSTGRES_URL", uri)
    with pytest.raises(NonLocalEndpointError):
        get_postgres_connection_string()


def test_connection_string_accepts_normal_userinfo(monkeypatch):
    # a single, ordinary userinfo@host must still work
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "postgresql://user:p,w@localhost:5432/db")
    assert get_postgres_connection_string().endswith("/db")


def test_redact_strips_dsn_password():
    out = redact_creds("OperationalError: host=localhost password=s3cr#t dbname=x failed")
    assert "s3cr#t" not in out and "password=***" in out


def test_configured_checkpointer_fails_loud_without_extra(monkeypatch):
    # langgraph absent -> RuntimeError naming the extra (postgres path). When langgraph IS
    # installed the postgres path instead reaches the backend (covered in the integration
    # suite via the memory path and a live-postgres test), so skip here.
    if importlib.util.find_spec("langgraph") is not None:
        pytest.skip("langgraph installed — real checkpointer paths covered by integration tests")
    monkeypatch.setenv("ASSAY_CHECKPOINT_BACKEND", "postgres")
    with pytest.raises(RuntimeError, match="persistence' extra"):
        configured_checkpointer()


def test_memory_checkpointer_fails_loud_without_extra():
    # the in-memory saver is also a langgraph type; without the extra it fails loud, not silent
    if importlib.util.find_spec("langgraph") is not None:
        pytest.skip("langgraph installed — exercises the absent-extra path")
    with pytest.raises(RuntimeError, match="persistence' extra"):
        get_checkpointer(use_memory=True)


# ---- vector store loopback ----


def test_vector_store_url_loopback():
    assert vector_store_url().startswith("http://localhost:")


def test_vector_store_rejects_non_loopback(monkeypatch):
    monkeypatch.setattr(vs, "VECTOR_HOST", "10.0.0.9")
    with pytest.raises(NonLocalEndpointError):
        vector_store_url()
    with pytest.raises(NonLocalEndpointError):
        get_qdrant_client()  # guard fires before importing qdrant_client


# ---- content-addressed versioning ----


def test_versioner_is_deterministic_and_addressable(tmp_path):
    store = tmp_path / "store"
    a = tmp_path / "a.txt"
    a.write_text("hello world")
    v = LocalDataVersioner(store_dir=str(store))
    digest1 = v.put(str(a))
    digest2 = v.fingerprint(str(a))
    assert digest1 == digest2  # put and fingerprint agree
    assert v.path_for(digest1).is_file()  # artifact is retrievable by id
    # identical bytes elsewhere -> identical id (content-addressed)
    b = tmp_path / "b.txt"
    b.write_text("hello world")
    assert v.put(str(b)) == digest1


def test_versioner_rejects_non_file(tmp_path):
    v = LocalDataVersioner(store_dir=str(tmp_path / "s"))
    with pytest.raises(FileNotFoundError):
        v.fingerprint(str(tmp_path / "missing"))


def test_versioner_path_for_rejects_traversal(tmp_path):
    # #112: path_for must reject non-digest ids that would escape the store
    v = LocalDataVersioner(store_dir=str(tmp_path / "s"))
    for bad in ["../../etc/passwd", "..", "a/b", "g" * 64, "abc", "/etc/passwd"]:
        with pytest.raises(ValueError, match="invalid version id"):
            v.path_for(bad)
    assert v.path_for("a" * 64).name == "a" * 64  # a valid digest is accepted


def test_vector_store_upsert_streams_batches_and_owns_client():
    import pytest as _pytest

    _pytest.importorskip("qdrant_client")
    from assay_engine.persistence.vectorstore import QdrantVectorStore

    class FakeClient:
        def __init__(self):
            self.batches = []
            self.closed = False

        def upsert(self, collection, points):
            self.batches.append(len(points))

        def close(self):
            self.closed = True

    fc = FakeClient()
    store = QdrantVectorStore("c", 2, client=fc)
    store.upsert([f"u{i}" for i in range(5)], [[0.0, 1.0]] * 5, batch_size=2)
    assert fc.batches == [2, 2, 1]  # #118: streamed in bounded batches
    with pytest.raises(ValueError):
        store.upsert(["u0"], [[0.0], [1.0]])  # length mismatch
    store.close()
    assert fc.closed is False  # #117: an INJECTED client is the caller's to close, not ours


def test_vector_store_closes_owned_client(monkeypatch):
    # #117: a self-created client (no client injected) MUST be closed on close()/context-exit
    pytest.importorskip("qdrant_client")
    from assay_engine.persistence import vectorstore as vs

    class FakeClient:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    created = FakeClient()
    monkeypatch.setattr(vs, "get_qdrant_client", lambda: created)
    with vs.QdrantVectorStore("c", 2) as store:  # no client injected → owns it
        assert store._owns_client is True
    assert created.closed is True  # owned client closed on context exit (leak prevented)


def test_vector_store_upsert_builds_one_batch_at_a_time():
    # #118: only one batch of PointStructs may be materialized at a time — assert construction is
    # interleaved with sends, not all-up-front.
    pytest.importorskip("qdrant_client")
    from assay_engine.persistence.vectorstore import QdrantVectorStore

    accessed: list[int] = []

    class TrackingVectors:
        def __init__(self, data):
            self._d = data

        def __len__(self):
            return len(self._d)

        def __getitem__(self, i):
            accessed.append(i)  # records when each vector is consumed
            return self._d[i]

    class FakeClient:
        def __init__(self):
            self.accessed_at_call = []

        def upsert(self, collection, points):
            self.accessed_at_call.append(len(accessed))  # how many vectors consumed so far

    fc = FakeClient()
    store = QdrantVectorStore("c", 2, client=fc)
    store.upsert([f"u{i}" for i in range(6)], TrackingVectors([[0.0, 1.0]] * 6), batch_size=2)
    # per-batch construction → 2,4,6 consumed at each send; all-up-front would be 6,6,6
    assert fc.accessed_at_call == [2, 4, 6]


# ---- hardened checkpointer invariants (fake backends injected, no Postgres) ----


@pytest.fixture
def fake_pg(monkeypatch):
    """Inject fake langgraph/psycopg modules so get_checkpointer runs the full hardened path
    offline, and reset the module's process-local bootstrap state."""
    import sys
    import types

    from assay_engine.persistence import checkpoint as cp

    state = {"setup_on": [], "lock_on": [], "pools": [], "atexit_registered": 0}

    class FakeConn:
        def execute(self, sql, params=None):
            if "pg_advisory_lock" in sql:
                state["lock_on"].append(id(self))

    class FakePool:
        check_connection = staticmethod(lambda *a, **k: None)

        def __init__(self, conn_str, **kw):
            self.conn_str = conn_str
            self._conn = FakeConn()
            state["pools"].append(self)

        def connection(self):
            conn = self._conn

            class _Ctx:
                def __enter__(self_):
                    return conn

                def __exit__(self_, *a):
                    return False

            return _Ctx()

        def close(self):
            pass

    class FakeSaver:
        def __init__(self, arg):
            self.arg = arg

        def setup(self):
            state["setup_on"].append(id(self.arg))

    def _mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        monkeypatch.setitem(sys.modules, name, m)
        return m

    _mod("langgraph")
    _mod("langgraph.checkpoint")
    _mod("langgraph.checkpoint.postgres", PostgresSaver=FakeSaver)
    _mod("langgraph.checkpoint.memory", MemorySaver=type("MemorySaver", (), {}))
    _mod("psycopg")
    _mod("psycopg.rows", dict_row=object())
    _mod("psycopg_pool", ConnectionPool=FakePool)

    # reset process-local bootstrap bookkeeping
    monkeypatch.setattr(cp, "_INITIALIZED_CONN_STRS", set())
    monkeypatch.setattr(cp, "_OPEN_POOLS", [])
    monkeypatch.setattr(cp, "_atexit_registered", False)
    monkeypatch.setattr(
        cp,
        "atexit",
        types.SimpleNamespace(
            register=lambda fn: state.__setitem__(
                "atexit_registered", state["atexit_registered"] + 1
            )
        ),
    )
    monkeypatch.setenv("ASSAY_POSTGRES_URL", "postgresql://localhost:5432/assay")
    return cp, state


def test_setup_runs_once_per_conn_and_on_locked_connection(fake_pg):
    cp, state = fake_pg
    cp.get_checkpointer()
    cp.get_checkpointer()  # second call, same conn_str
    # setup() ran exactly once despite two factory calls (once-per-conn guard)
    assert len(state["setup_on"]) == 1
    # the advisory lock and the DDL ran on the SAME connection object
    assert state["lock_on"] == state["setup_on"]


def test_atexit_pool_cleanup_registered_once(fake_pg):
    cp, state = fake_pg
    cp.get_checkpointer()
    cp.get_checkpointer()
    # two pools opened and tracked, but only one shared atexit handler registered
    assert len(state["pools"]) == 2
    assert len(cp._OPEN_POOLS) == 2
    assert state["atexit_registered"] == 1


def test_pool_closed_and_unregistered_when_bootstrap_fails(fake_pg):
    # #105: if schema bootstrap fails AFTER the pool opened, the pool must be closed and dropped
    # from the cleanup registry — not leaked.
    import sys

    cp, state = fake_pg
    closed: list = []
    Pool = sys.modules["psycopg_pool"].ConnectionPool
    orig_close = Pool.close
    Pool.close = lambda self: (closed.append(self), orig_close(self))[1]  # record close
    Saver = sys.modules["langgraph.checkpoint.postgres"].PostgresSaver
    orig_setup = Saver.setup

    def boom(self):
        raise RuntimeError("setup failed (schema DDL)")

    Saver.setup = boom
    try:
        with pytest.raises(RuntimeError, match="connection failed"):
            cp.get_checkpointer()
        assert len(state["pools"]) == 1  # a pool was opened
        assert closed and closed[0] is state["pools"][0]  # and it was closed
        assert cp._OPEN_POOLS == []  # and removed from the cleanup registry (no leak)
    finally:
        Pool.close = orig_close
        Saver.setup = orig_setup


def test_connection_failure_redacts_and_leaks_no_context(fake_pg, monkeypatch):
    # issue #P2: on failure the credential-bearing original must be retained as neither
    # __cause__ nor __context__, and the message must be redacted.
    import sys

    cp, _ = fake_pg
    conn = "postgresql://admin:SUPERSECRET@127.0.0.1:5432/x"
    monkeypatch.setenv("ASSAY_POSTGRES_URL", conn)

    def boom(*a, **k):
        raise OSError(f"could not connect using {conn}")

    monkeypatch.setattr(sys.modules["psycopg_pool"], "ConnectionPool", boom)
    with pytest.raises(RuntimeError) as ei:
        cp.get_checkpointer()
    err = ei.value
    assert "SUPERSECRET" not in str(err)
    assert err.__cause__ is None and err.__context__ is None  # no credential-bearing original


def test_versioner_publish_leaves_no_temp_files(tmp_path):
    # atomic publish must not leave .tmp- scratch behind, and an empty file is versionable
    store = tmp_path / "store"
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    v = LocalDataVersioner(store_dir=str(store))
    digest = v.put(str(empty))
    assert v.path_for(digest).is_file()
    leftovers = [p.name for p in store.rglob(".tmp-*")]
    assert leftovers == []
