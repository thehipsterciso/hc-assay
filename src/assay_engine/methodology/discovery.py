"""Discovery runner — Firewall B (discover/confirm separation) enforced by construction.

The mirror of :mod:`assay_engine.methodology.adjudication`. In discovery mode the data surfaces
candidate hypotheses; Firewall B (METHODOLOGY.md §2, ADR-0005) requires that the data used to
*discover* a hypothesis is not the data used to *confirm* it — otherwise discovering a pattern
and "testing" it on the same data proves nothing.

The engine had the split primitive (:class:`DiscoverConfirmSplit`) and a confirm step that
refuses discovery ids, but no composition — so the separation held only if a study wired it by
hand (same risk Firewall A had before ADR-0008). :func:`discover_and_confirm` makes it
structural: it hands the ``discover`` step a corpus containing *only* the discovery partition
and the ``confirm`` step a corpus containing *only* the held-out partition, so neither step can
accidentally use the other's data.

Honest scope (lesson from the adjudication review, ADR-0008): the engine partitions the
**structural** data — units, and relations whose *both* endpoints are in the partition. It
does NOT carry the corpus's free-form ``metadata`` into a subset (an arbitrary mapping cannot
be partitioned safely — a per-unit index in metadata would otherwise leak the other partition
wholesale), and it cannot police free-text inside ``Unit``/``Relation.attributes`` that an
adapter might use to reference units outside the partition. So: the structural separation is
enforced; keeping per-unit data out of metadata/attribute *payloads* is the adapter's
obligation (the Firewall-B analogue of the corpus-content caveat in ADR-0005). And, as with
adjudication, this is a *signature-level* guarantee — it prevents accidental double-dipping,
not a step that willfully reflects into the caller's frame (only process isolation could).
"""

from __future__ import annotations

from typing import Callable, Iterable, Protocol

from assay_engine.contracts.schema import Corpus
from assay_engine.methodology.confirm import require_locked
from assay_engine.methodology.firewalls import DiscoverConfirmSplit, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisOrigin
from assay_engine.methodology.verdict import Verdict


class HeldOutConfirmer(Protocol):
    """Study-supplied: confirm one locked, data-surfaced hypothesis on the held-out corpus."""

    def __call__(self, hypothesis: Hypothesis, held_out: Corpus) -> Verdict: ...


def subset_corpus(corpus: Corpus, ids: Iterable[str]) -> Corpus:
    """Return the sub-corpus of ``corpus`` restricted to ``ids``.

    Units not in ``ids`` are dropped; a relation is kept only if *both* endpoints are in
    ``ids`` (a relation to a unit outside the partition would leak that unit's existence/links
    into the partition).

    Corpus-level ``metadata`` is deliberately **dropped**, not carried through: it is an
    arbitrary mapping the engine cannot partition safely. A per-unit index living in metadata
    (e.g. ``{"by_unit": {unit_id: ...}}``) would otherwise hand the discovery step the held-out
    partition wholesale — silently defeating Firewall B. Adapters that need partition-scoped
    side data must put it on the ``Unit``/``Relation`` records (which *are* partitioned), not in
    corpus metadata; free-text inside ``attributes`` that references foreign units remains the
    adapter's obligation (ADR-0005 / ADR-0008 honest-scope caveat).
    """
    keep = frozenset(ids)
    units = tuple(u for u in corpus.units if u.unit_id in keep)
    relations = tuple(
        r for r in corpus.relations if r.source_id in keep and r.target_id in keep
    )
    return Corpus(units=units, relations=relations)


def discover_and_confirm(
    corpus: Corpus,
    split: DiscoverConfirmSplit,
    *,
    discover: Callable[[Corpus], Iterable[Hypothesis]],
    confirm: HeldOutConfirmer,
) -> list[Verdict]:
    """Run discovery then confirmation with the data separation enforced by construction.

    1. ``discover`` is handed a corpus containing only the discovery partition and returns
       candidate hypotheses. They must be ``DISCOVERY``-origin and **locked** (pre-registered)
       before confirmation — discovering and confirming on the same data, or confirming an
       unlocked hypothesis, is the double-dipping Firewall B exists to prevent.
    2. ``confirm`` is handed a corpus containing only the held-out partition and tests each
       hypothesis there; the verdict must report the hypothesis it answers.

    Returns the verdicts. Raises ``FirewallViolation`` on an empty discovery or held-out
    partition (split ids that select no corpus units — a vacuous test), a non-``DISCOVERY``
    hypothesis, an unlocked hypothesis, or a verdict↔hypothesis misattribution.
    """
    discovery_corpus = subset_corpus(corpus, split.discovery_ids)
    if not discovery_corpus.units:
        # the discovery partition selects no actual corpus units — a hypothesis "discovered"
        # from zero data is not data-surfaced at all; it would confirm cleanly on the held-out
        # set and silently launder a hand-authored claim through Firewall B. Fail loud.
        raise FirewallViolation(
            "discovery partition selects no corpus units — nothing to discover from "
            "(do split ids match the corpus unit ids?)"
        )
    hypotheses = list(discover(discovery_corpus))  # sees only the discovery partition

    held_out = subset_corpus(corpus, split.confirm_ids)  # disjoint from discovery (split invariant)
    if not held_out.units:
        # the confirmation partition selects no actual corpus units — confirming on an empty
        # held-out set is a vacuous test (the split ids don't match the corpus). Fail loud.
        raise FirewallViolation(
            "confirmation partition selects no corpus units — nothing to confirm on "
            "(do split ids match the corpus unit ids?)"
        )
    verdicts: list[Verdict] = []
    for hypothesis in hypotheses:
        if hypothesis.origin is not HypothesisOrigin.DISCOVERY:
            raise FirewallViolation(
                f"hypothesis {hypothesis.hypothesis_id!r} is {hypothesis.origin.value!r}; the "
                "discovery runner expects DISCOVERY-origin (data-surfaced) hypotheses"
            )
        require_locked(hypothesis)  # must be pre-registered before it is confirmed (Firewall B)
        verdict = confirm(hypothesis, held_out)
        if verdict.hypothesis_id != hypothesis.hypothesis_id:
            raise FirewallViolation(
                f"verdict reports hypothesis_id {verdict.hypothesis_id!r} for hypothesis "
                f"{hypothesis.hypothesis_id!r} — hypothesis↔verdict misattribution"
            )
        verdicts.append(verdict)
    return verdicts
