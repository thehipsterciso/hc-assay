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

import datetime as _dt
from typing import Callable, Iterable, Protocol

from assay_engine.contracts.schema import Corpus
from assay_engine.methodology.firewalls import DiscoverConfirmSplit, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisOrigin
from assay_engine.methodology.preregistration import (
    TimestampAuthority,
    require_preregistered,
)
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
    relations = tuple(r for r in corpus.relations if r.source_id in keep and r.target_id in keep)
    return Corpus(units=units, relations=relations)


def discover_and_confirm(
    corpus: Corpus,
    split: DiscoverConfirmSplit,
    *,
    discover: Callable[[Corpus], Iterable[Hypothesis]],
    confirm: HeldOutConfirmer,
    authority: TimestampAuthority,
) -> list[Verdict]:
    """Run discovery then confirmation with the data separation enforced by construction.

    1. ``discover`` is handed a corpus containing only the discovery partition and returns
       candidate hypotheses. They must be ``DISCOVERY``-origin and genuinely **pre-registered**
       before confirmation — ``require_preregistered`` checks (via ``authority``) that the proof
       binds each hypothesis's content and that its attested lock time precedes confirmation.
       Discovering and confirming on the same data, or confirming a hypothesis whose content was
       changed after locking, is the double-dipping Firewall B exists to prevent.
    2. ``confirm`` is handed a corpus containing only the held-out partition and tests each
       hypothesis there; the verdict must report the hypothesis it answers.

    Firewall B is enforced STRUCTURALLY here (pass 5, #H-016): the ``confirm`` step physically
    receives a held-out-only corpus, so it cannot evaluate a discovery-partition unit even if it
    wanted to — discovery ids are simply not present. The per-id ``DiscoverConfirmSplit.
    assert_confirm_only`` check used by :func:`confirm_unit_level` is an ADDITIONAL belt-and-braces
    guard a study layers inside its own confirmer; this runner does not (and cannot) call it
    because it does not know which evaluated ids the study's confirmer touched.

    ``authority`` is the pre-registration timestamp authority (e.g.
    :class:`~assay_engine.methodology.preregistration.LocalHmacAuthority`, or an RFC-3161
    adapter); the engine ships no silent-accept default. A study's ``discover`` step locks each
    discovered hypothesis (e.g. via :func:`~assay_engine.methodology.preregistration.
    lock_hypothesis`) before returning it.

    Returns the verdicts. Raises ``FirewallViolation`` (incl. ``PreRegistrationError``) on an
    empty discovery or held-out partition (split ids that select no corpus units — a vacuous
    test), a non-``DISCOVERY`` hypothesis, a hypothesis that is not verifiably pre-registered
    before confirmation, or a verdict↔hypothesis misattribution.
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
    if not hypotheses:
        # discovery surfaced nothing — a discovery run with zero hypotheses produces no
        # confirmatory verdict at all and is indistinguishable from a silently broken
        # ``discover`` callable that forgot to return. Fail loud rather than complete vacuously
        # (pass 3, #F-042; mirrors the empty-partition guards above).
        raise FirewallViolation(
            "discover() returned no hypotheses — a discovery run with zero hypotheses is "
            "vacuous and cannot produce a confirmatory verdict"
        )

    held_out = subset_corpus(corpus, split.confirm_ids)  # disjoint from discovery (split invariant)
    if not held_out.units:
        # the confirmation partition selects no actual corpus units — confirming on an empty
        # held-out set is a vacuous test (the split ids don't match the corpus). Fail loud.
        raise FirewallViolation(
            "confirmation partition selects no corpus units — nothing to confirm on "
            "(do split ids match the corpus unit ids?)"
        )
    verdicts: list[Verdict] = []
    # within-run hypothesis uniqueness (pass 3, #F-018): a ``discover`` step returning the same
    # hypothesis_id twice would append two verdicts for one hypothesis, inflating the verdict
    # count. The pipeline runner guards this via ``_require_unique_ids``; mirror it in the
    # public standalone runner so both entry points enforce the same identity invariant.
    seen_hypothesis_ids: set[str] = set()
    for hypothesis in hypotheses:
        if hypothesis.hypothesis_id in seen_hypothesis_ids:
            raise FirewallViolation(
                f"duplicate hypothesis_id {hypothesis.hypothesis_id!r} returned by discover() — "
                "each discovered hypothesis must have a unique id"
            )
        seen_hypothesis_ids.add(hypothesis.hypothesis_id)
        if hypothesis.origin is not HypothesisOrigin.DISCOVERY:
            raise FirewallViolation(
                f"hypothesis {hypothesis.hypothesis_id!r} is {hypothesis.origin.value!r}; the "
                "discovery runner expects DISCOVERY-origin (data-surfaced) hypotheses"
            )
        # Pre-registration enforced by the runner: the proof must bind THIS hypothesis's content
        # (no post-lock content swap) and its attested lock time must precede this confirmation.
        require_preregistered(
            hypothesis, authority=authority, not_after=_dt.datetime.now(tz=_dt.timezone.utc)
        )
        verdict = confirm(hypothesis, held_out)
        # A confirmer that forgets to `return` yields None; accessing verdict.hypothesis_id would
        # raise an opaque AttributeError instead of a typed firewall error (pass 4, #G-011 —
        # mirrors the pipeline/adjudication guards from #F-021).
        if not isinstance(verdict, Verdict):
            raise FirewallViolation(
                f"confirm returned {type(verdict).__name__} for hypothesis "
                f"{hypothesis.hypothesis_id!r} — expected a Verdict"
            )
        if verdict.hypothesis_id != hypothesis.hypothesis_id:
            raise FirewallViolation(
                f"verdict reports hypothesis_id {verdict.hypothesis_id!r} for hypothesis "
                f"{hypothesis.hypothesis_id!r} — hypothesis↔verdict misattribution"
            )
        verdicts.append(verdict)
    return verdicts
