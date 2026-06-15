"""Persistence — durable run state, data versioning, vector store (all local).

- ``checkpoint`` — durable checkpointing of run state so a study can resume.
- ``versioning`` — content-addressed data versioning for inputs and artifacts.
- ``vectorstore`` — a local vector store for embedding-based baseline builders.

All on-box (ADR-0003). Lifted from the prior platform's hardened persistence layer (durable
checkpointer + data versioning + local vector store).
"""

from assay_engine.persistence.checkpoint import Checkpointer
from assay_engine.persistence.vectorstore import VectorStore
from assay_engine.persistence.versioning import DataVersioner

__all__ = ["Checkpointer", "VectorStore", "DataVersioner"]
