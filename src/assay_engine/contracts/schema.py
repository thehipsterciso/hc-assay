"""Canonical schema — the dataset-agnostic shape the baseline is built from.

An adapter's job is to turn its raw source into a :class:`Corpus` of these types. The engine
builds the baseline from a ``Corpus`` and never sees the source's native format.

Firewall A boundary (critical):
    A ``Corpus`` carries the *data itself* — units of text/attributes and any structure that
    is intrinsic to the raw source. It must **not** carry an external authority's *judgments*
    about the data (asserted relationships, strengths, labels, a taxonomy). Those are claims;
    they travel through :mod:`assay_engine.contracts.claims`, quarantined from baseline
    construction. If an adapter is tempted to put an external mapping into ``Corpus.relations``,
    that is a Firewall A violation — it belongs in the claims source instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


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
