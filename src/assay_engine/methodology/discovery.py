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

Honest scope (same as ADR-0008): this is a **signature-level** guarantee — each step is handed
only its subset, preventing *accidental* leakage. It is not isolation against a step that
deliberately reflects into the caller's frame; only process isolation would prevent that, which
is out of scope. The guarantee is against accidental double-dipping, not willful circumvention.
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
    into the partition). Metadata is carried through unchanged — adapters must keep external
    judgements out of metadata regardless (ADR-0005 / schema contract).
    """
    keep = frozenset(ids)
    units = tuple(u for u in corpus.units if u.unit_id in keep)
    relations = tuple(
        r for r in corpus.relations if r.source_id in keep and r.target_id in keep
    )
    return Corpus(units=units, relations=relations, metadata=corpus.metadata)


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

    Returns the verdicts. Raises ``FirewallViolation`` on a non-``DISCOVERY`` hypothesis, an
    unlocked hypothesis, or a verdict↔hypothesis misattribution.
    """
    discovery_corpus = subset_corpus(corpus, split.discovery_ids)
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
