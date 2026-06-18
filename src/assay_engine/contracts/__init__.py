"""The engine ↔ adapter contract.

This subpackage is the stable boundary of the blueprint. The engine depends *only* on the
types and Protocols defined here; adapters implement them. Per ARCHITECTURE.md §3:

- The engine imports no adapter module.
- Adapters depend on the engine, never the reverse, and never on each other.
- The external-claims source is structurally separable, so the baseline pipeline can run
  with it withheld — that is how Firewall A (claim-blindness) is enforced, not just
  promised.
"""

from assay_engine.contracts.claims import ClaimRecord, ExternalClaimsSource
from assay_engine.contracts.features import FeatureBuilder, FeatureMatrix
from assay_engine.contracts.parser import IngestionParser
from assay_engine.contracts.prompts import PromptManifest, prompt_manifest
from assay_engine.contracts.schema import Corpus, Relation, Unit
from assay_engine.contracts.study import StudyDefinition, StudyMode

__all__ = [
    "ClaimRecord",
    "ExternalClaimsSource",
    "FeatureBuilder",
    "FeatureMatrix",
    "IngestionParser",
    "PromptManifest",
    "prompt_manifest",
    "Corpus",
    "Relation",
    "Unit",
    "StudyDefinition",
    "StudyMode",
]
