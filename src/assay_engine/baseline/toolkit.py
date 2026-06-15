"""Baseline builder contract + a deterministic artifact wrapper.

The builders (embeddings, similarity, graph, clustering, stats) are implemented as the
engine matures; this module fixes the *shape* of a baseline artifact and the build contract
so the rest of the engine (gates, confirm, provenance) can be wired against it now.

Firewall A is enforced here structurally: :meth:`BaselineBuilder.build` accepts a
:class:`~assay_engine.methodology.firewalls.ClaimBlindGuard` and never accepts a claims
source — a baseline simply cannot be handed the claims it must stay blind to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from assay_engine.contracts.schema import Corpus
from assay_engine.methodology.firewalls import ClaimBlindGuard


@dataclass(frozen=True, slots=True)
class BaselineArtifact:
    """A deterministic, versioned empirical model of the corpus — the one privileged object.

    Concrete contents (embedding matrices, similarity graphs, cluster assignments, etc.) live
    under ``contents`` keyed by builder name. ``determinism`` records the seeds, input hashes,
    and model/version strings needed to reproduce it.
    """

    corpus_fingerprint: str
    contents: Mapping[str, Any]
    determinism: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class BaselineBuilder(Protocol):
    """Build a :class:`BaselineArtifact` from a corpus, blind to any external claims."""

    def build(self, corpus: Corpus, *, claim_guard: ClaimBlindGuard) -> BaselineArtifact:
        """Construct the baseline. Must run with ``claim_guard.sealed()`` in force."""
        ...
