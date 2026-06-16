"""Baseline builder contract + a deterministic artifact wrapper.

This module fixes the *shape* of a baseline artifact and the build contract. The engine ships
the dataset-agnostic building blocks for a baseline (similarity/distance, descriptive stats,
the determinism harness in :mod:`assay_engine.baseline`); the choice-bearing builder that
assembles them — which embedding model, which clustering, which graph — encodes dataset
decisions and is supplied by a study's adapter as a :class:`BaselineBuilder` (ADR-0002).

Firewall A is enforced here structurally: :meth:`BaselineBuilder.build` accepts a
:class:`~assay_engine.methodology.firewalls.ClaimBlindGuard` and never accepts a claims
source — a baseline simply cannot be handed the claims it must stay blind to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from assay_engine._frozen import freeze_mapping
from assay_engine.contracts.claims import ExternalClaimsSource
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "contents", freeze_mapping(self.contents))
        object.__setattr__(self, "determinism", freeze_mapping(self.determinism))


class BaselineBuilder(Protocol):
    """Build a :class:`BaselineArtifact` from a corpus, blind to any external claims."""

    def build(
        self, corpus: Corpus, *, claim_guard: ClaimBlindGuard[ExternalClaimsSource]
    ) -> BaselineArtifact:
        """Construct the baseline. Must run with ``claim_guard.sealed()`` in force."""
        ...
