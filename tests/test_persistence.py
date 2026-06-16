"""Persistence port — credential redaction, loopback, content-addressing (offline)."""

import pytest

from assay_engine._local import NonLocalEndpointError
from assay_engine.persistence import vectorstore as vs
from assay_engine.persistence.checkpoint import (
    _sanitize_conn_str,
    configured_checkpointer,
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


@pytest.mark.parametrize(
    "pw", ["plain", "p/w", "p w", "p@ss", "s3cr#t!"]
)
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


def test_configured_checkpointer_fails_loud_without_extra(monkeypatch):
    # langgraph absent in this env -> RuntimeError naming the extra (postgres path)
    monkeypatch.setenv("ASSAY_CHECKPOINT_BACKEND", "postgres")
    with pytest.raises(RuntimeError, match="persistence' extra"):
        configured_checkpointer()


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
