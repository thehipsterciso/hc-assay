"""assay_engine — the reusable, dataset-agnostic engine of the hc-assay blueprint.

The single architectural rule (ADR-0002, ARCHITECTURE.md §3):

    The engine never imports dataset specifics. Adapters implement the interfaces in
    ``assay_engine.contracts`` that the engine calls. A clone is: implement the adapter,
    register it, run.

This package contains only goal-agnostic machinery:

- ``contracts``      — the engine ↔ adapter boundary (canonical schema + adapter Protocols).
- ``methodology``    — hypotheses, the three verdicts, the two firewalls, the
                       measurement↔interpretation fence, confirmatory-test machinery.
- ``baseline``       — dataset-agnostic primitives (similarity/distance, descriptive stats) and
                       a determinism/reproducibility harness — the raw material; choice-bearing
                       builders (embeddings, clustering, graph/topology) are supplied per study by
                       the adapter's BaselineBuilder (ADR-0002).
- ``orchestration``  — the analysis graph, phase machine, and governance gates.
- ``reasoning``      — the tiered LLM reasoning seam.
- ``observability``  — self-hosted tracing + experiment tracking.
- ``persistence``    — durable checkpointing, data versioning, vector store.
- ``provenance``     — the append-only, hash-chained audit trail (GOVERNANCE §3).
- ``pipeline``       — ``run_study``: the composed, governed end-to-end runner (ADR-0010).
- ``registry``       — adapter registration.

Nothing in this package may import an adapter module or name a specific dataset, authority,
or taxonomy.
"""

__version__ = "0.0.1"

# Public API — the surface a cloning study uses. Heavy/optional backends stay behind their
# subpackages (imported lazily there); these names are dependency-free to import.
from assay_engine.contracts import (  # noqa: E402
    ClaimRecord,
    Corpus,
    ExternalClaimsSource,
    FeatureBuilder,
    FeatureMatrix,
    IngestionParser,
    Relation,
    StudyDefinition,
    StudyMode,
    Unit,
)
from assay_engine.pipeline import (  # noqa: E402
    GateHandler,
    GateReview,
    IngestionError,
    StudyPlan,
    StudyResult,
    auto_approve,
    run_study,
)
from assay_engine.provenance import (  # noqa: E402
    ProvenanceEntry,
    ProvenanceError,
    ProvenanceTrail,
    from_records,
    verify_records,
)
from assay_engine.registry import (  # noqa: E402
    get_study,
    register_study,
    registered_studies,
)

__all__ = [
    "__version__",
    # contracts
    "ClaimRecord",
    "Corpus",
    "ExternalClaimsSource",
    "FeatureBuilder",
    "FeatureMatrix",
    "IngestionParser",
    "Relation",
    "StudyDefinition",
    "StudyMode",
    "Unit",
    # pipeline
    "GateHandler",
    "GateReview",
    "IngestionError",
    "StudyPlan",
    "StudyResult",
    "auto_approve",
    "run_study",
    # provenance
    "ProvenanceEntry",
    "ProvenanceError",
    "ProvenanceTrail",
    "from_records",
    "verify_records",
    # registry
    "get_study",
    "register_study",
    "registered_studies",
]
