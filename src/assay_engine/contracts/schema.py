"""Canonical schema — the dataset-agnostic shape the baseline is built from.

An adapter's job is to turn its raw source into a :class:`Corpus` of these types. The engine
builds the baseline from a ``Corpus`` and never sees the source's native format.

Firewall A boundary (an adapter obligation, not a type-enforced guarantee):
    A ``Corpus`` carries the *data itself* — units of text/attributes and any structure that
    is intrinsic to the raw source. It must **not** carry an external authority's *judgments*
    about the data (asserted relationships, strengths, labels, a taxonomy). Those are claims;
    they travel through :mod:`assay_engine.contracts.claims`, quarantined from baseline
    construction. Putting an external mapping into ``Corpus.relations`` (or external labels
    into ``attributes``/``metadata``) is a Firewall A violation.

    Because the mapping/relation payloads are deliberately open (the engine is
    dataset-agnostic), this boundary is an **adapter contract obligation** the type system
    cannot enforce — not a structural guarantee. The structural guarantees of Firewall A are
    that the baseline builder is never handed an ``ExternalClaimsSource`` and that
    ``StudyDefinition`` refuses a claims source outside adjudication mode (audit pass 1,
    issues #1, #3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from assay_engine._frozen import freeze_mapping


@dataclass(frozen=True, slots=True)
class Unit:
    """One analyzable object in the corpus (a document, record, entity, item).

    ``unit_id`` is stable and unique within the corpus. ``text`` is the natural-language
    content the NLP baseline operates on (may be empty for non-text units). ``attributes``
    holds structured fields intrinsic to the data — never an external authority's verdicts.
    """

    unit_id: str
    text: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)
    source_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", freeze_mapping(self.attributes))


@dataclass(frozen=True, slots=True)
class Relation:
    """A relationship that is *intrinsic to the raw data* (not an external judgment).

    Example of legitimate use: a parent/child link the source file itself encodes. Example of
    illegitimate use: an external expert's asserted mapping between units — that is a claim
    (see :mod:`assay_engine.contracts.claims`) and must be withheld from the baseline.
    """

    source_id: str
    target_id: str
    kind: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", freeze_mapping(self.attributes))


@dataclass(frozen=True, slots=True)
class Corpus:
    """The full canonical dataset handed to the baseline builder."""

    units: tuple[Unit, ...]
    relations: tuple[Relation, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def unit_ids(self) -> frozenset[str]:
        return frozenset(u.unit_id for u in self.units)

    def __post_init__(self) -> None:
        ids = [u.unit_id for u in self.units]
        if len(ids) != len(set(ids)):
            raise ValueError("Corpus contains duplicate unit_id values")
        # A closed canonical corpus must not contain relations to non-existent units
        # (audit pass 1, issue #3) — mirrors the duplicate-id and FeatureMatrix checks.
        known = set(ids)
        dangling = sorted(
            {e for r in self.relations for e in (r.source_id, r.target_id) if e not in known}
        )
        if dangling:
            raise ValueError(
                f"Corpus has relations referencing unknown unit_id(s): {dangling[:5]}"
            )
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
