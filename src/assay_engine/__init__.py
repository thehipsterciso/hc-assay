"""assay_engine — the reusable, dataset-agnostic engine of the hc-assay blueprint.

The single architectural rule (ADR-0002, ARCHITECTURE.md §3):

    The engine never imports dataset specifics. Adapters implement the interfaces in
    ``assay_engine.contracts`` that the engine calls. A clone is: implement the adapter,
    register it, run.

This package contains only goal-agnostic machinery:

- ``contracts``      — the engine ↔ adapter boundary (canonical schema + adapter Protocols).
- ``methodology``    — hypotheses, the three verdicts, the two firewalls, the
                       measurement↔interpretation fence, confirmatory-test machinery.
- ``baseline``       — dataset-agnostic baseline builders (embeddings, similarity, graph,
                       clustering, descriptive stats).
- ``orchestration``  — the analysis graph, phase machine, and governance gates.
- ``reasoning``      — the tiered LLM reasoning seam.
- ``observability``  — self-hosted tracing + experiment tracking.
- ``persistence``    — durable checkpointing, data versioning, vector store.
- ``registry``       — adapter registration.

Nothing in this package may import an adapter module or name a specific dataset, authority,
or taxonomy.
"""

__version__ = "0.0.1"
