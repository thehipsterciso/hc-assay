"""Persistence — durable run state, data versioning, vector store (all local, ADR-0003).

- ``checkpoint`` — engine phase-state Protocol + the hardened LangGraph checkpointer factory
  (loopback-enforced connection, credential redaction).
- ``versioning`` — content-addressed local artifact store (deterministic, offline).
- ``vectorstore`` — loopback-enforced local vector store factory.

Backends (langgraph-checkpoint-postgres, psycopg, qdrant-client) are optional (the
``persistence`` extra) and imported lazily; the security-critical logic is pure and tested.
"""

from assay_engine.persistence.checkpoint import (
    Checkpointer,
    configured_checkpointer,
    get_postgres_connection_string,
    redact_creds,
)
from assay_engine.persistence.vectorstore import (
    VectorStore,
    get_qdrant_client,
    vector_store_url,
)
from assay_engine.persistence.versioning import DataVersioner, LocalDataVersioner

__all__ = [
    "Checkpointer",
    "configured_checkpointer",
    "get_postgres_connection_string",
    "redact_creds",
    "VectorStore",
    "get_qdrant_client",
    "vector_store_url",
    "DataVersioner",
    "LocalDataVersioner",
]
