"""Persistence — durable run state, data versioning, vector store (all local, ADR-0003).

- ``checkpoint`` — the hardened LangGraph checkpointer factory: loopback-enforced connection,
  self-healing pool, advisory-locked one-time schema setup, credential redaction. (The
  returned object is a LangGraph ``BaseCheckpointSaver``, the real run-state mechanism the
  orchestration graph uses — the engine does not re-declare a competing save/load contract.)
- ``versioning`` — content-addressed local artifact store (deterministic, offline; ADR-0007).
- ``vectorstore`` — loopback-enforced local vector store factory.

Backends (langgraph-checkpoint-postgres, psycopg, qdrant-client) are optional (the
``persistence`` extra) and imported lazily (ADR-0006); the security-critical logic is pure
and unit-tested offline.
"""

from assay_engine.persistence.checkpoint import (
    configured_checkpointer,
    get_checkpointer,
    get_postgres_connection_string,
    redact_creds,
)
from assay_engine.persistence.vectorstore import (
    QdrantVectorStore,
    VectorStore,
    get_qdrant_client,
    vector_store_url,
)
from assay_engine.persistence.versioning import DataVersioner, LocalDataVersioner

__all__ = [
    "configured_checkpointer",
    "get_checkpointer",
    "get_postgres_connection_string",
    "redact_creds",
    "VectorStore",
    "QdrantVectorStore",
    "get_qdrant_client",
    "vector_store_url",
    "DataVersioner",
    "LocalDataVersioner",
]
