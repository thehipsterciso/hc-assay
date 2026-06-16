"""Discovery runner — Firewall B (discover/confirm separation) enforced by construction.

The tests ARE the enforcement: the discover step must be handed only the discovery partition,
the confirm step only the held-out partition, and misuse (non-discovery / unlocked hypothesis,
misattributed verdict) must be structurally caught.
"""

import datetime as _dt

import pytest

from assay_engine.contracts.schema import Corpus, Relation, Unit
from assay_engine.methodology.discovery import discover_and_confirm, subset_corpus
from assay_engine.methodology.firewalls import DiscoverConfirmSplit, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import LocalHmacAuthority, lock_hypothesis
from assay_engine.methodology.verdict import Verdict, VerdictLabel

# Real pre-registration authority for the tests: discovered hypotheses must be genuinely locked
# (the runner verifies the content-binding proof and lock-before-confirm ordering).
_AUTH = LocalHmacAuthority(b"discovery-test-secret-key-000001")
_LOCK_INSTANT = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(hours=1)


def _corpus():
    return Corpus(
        units=tuple(Unit(f"u{i}", f"t{i}") for i in range(6)),
        relations=(Relation("u0", "u1", "r"), Relation("u0", "u3", "cross")),
        # a per-unit index in corpus metadata is exactly the Firewall-B leak vector:
        # if subset_corpus carried this through, the discovery step would see the held-out units.
        metadata={"by_unit": {f"u{i}": f"secret-{i}" for i in range(6)}},
    )


def _split():
    return DiscoverConfirmSplit.from_partition({"u0", "u1", "u2"}, {"u3", "u4", "u5"})


def _locked_discovery(hid="H1"):
    return lock_hypothesis(
        Hypothesis(
            hypothesis_id=hid,
            statement="pattern",
            kind=HypothesisKind.UNIT_LEVEL,
            origin=HypothesisOrigin.DISCOVERY,
            test_name="t",
            decision_rule="r",
        ),
        authority=_AUTH,
        instant=_LOCK_INSTANT,
    )


# ---- subset_corpus ----


def test_subset_keeps_only_partition_units_and_internal_relations():
    sub = subset_corpus(_corpus(), {"u0", "u1", "u2"})
    assert {u.unit_id for u in sub.units} == {"u0", "u1", "u2"}
    # the u0->u1 relation is internal (kept); the u0->u3 cross-partition relation is dropped
    assert [(r.source_id, r.target_id) for r in sub.relations] == [("u0", "u1")]


def test_subset_drops_corpus_metadata():
    # corpus metadata can hold a per-unit index covering the WHOLE corpus; carrying it into a
    # subset would leak the held-out partition into the discovery step. It must be dropped.
    sub = subset_corpus(_corpus(), {"u0", "u1", "u2"})
    assert not sub.metadata  # empty/falsy — the foreign-unit index is gone


# ---- Firewall B by construction ----


def test_discover_sees_only_discovery_partition_confirm_only_held_out():
    seen = {}

    def discover(discovery_corpus):
        seen["discover_ids"] = {u.unit_id for u in discovery_corpus.units}
        seen["discover_metadata"] = dict(discovery_corpus.metadata)
        return [_locked_discovery()]

    def confirm(hypothesis, held_out):
        seen["confirm_ids"] = {u.unit_id for u in held_out.units}
        return Verdict(hypothesis.hypothesis_id, VerdictLabel.SUPPORTED, "r")

    discover_and_confirm(_corpus(), _split(), discover=discover, confirm=confirm, authority=_AUTH)
    assert seen["discover_ids"] == {"u0", "u1", "u2"}  # discovery never sees held-out data
    assert seen["confirm_ids"] == {"u3", "u4", "u5"}  # confirm never sees discovery data
    assert seen["discover_ids"].isdisjoint(seen["confirm_ids"])
    # the corpus-level per-unit index (covering u0..u5) must NOT reach the discovery step
    assert not seen["discover_metadata"]


def test_rejects_non_discovery_hypothesis():
    def discover(_c):
        return [
            Hypothesis(
                hypothesis_id="H1",
                statement="x",
                kind=HypothesisKind.UNIT_LEVEL,
                origin=HypothesisOrigin.EXTERNAL_CLAIM,
                test_name="t",
                decision_rule="r",
                source_claim_id="c1",
                locked_at="t",
                timestamp_proof="p",
            )
        ]

    with pytest.raises(FirewallViolation, match="DISCOVERY"):
        discover_and_confirm(
            _corpus(),
            _split(),
            discover=discover,
            confirm=lambda h, c: Verdict.supported(h.hypothesis_id, "r"),
            authority=_AUTH,
        )


def test_rejects_unlocked_hypothesis():
    def discover(_c):
        return [
            Hypothesis(
                hypothesis_id="H1",
                statement="x",
                kind=HypothesisKind.UNIT_LEVEL,
                origin=HypothesisOrigin.DISCOVERY,
                test_name="t",
                decision_rule="r",
            )
        ]

    with pytest.raises(FirewallViolation):  # require_locked: not pre-registered
        discover_and_confirm(
            _corpus(),
            _split(),
            discover=discover,
            confirm=lambda h, c: Verdict.supported(h.hypothesis_id, "r"),
            authority=_AUTH,
        )


def test_rejects_misattributed_verdict():
    with pytest.raises(FirewallViolation, match="misattribution"):
        discover_and_confirm(
            _corpus(),
            _split(),
            discover=lambda c: [_locked_discovery("H1")],
            confirm=lambda h, c: Verdict.supported("WRONG-H", "r"),
            authority=_AUTH,
        )


def test_rejects_held_out_partition_absent_from_corpus():
    # split confirm_ids that don't match any corpus unit -> empty held-out -> vacuous test
    bad_split = DiscoverConfirmSplit.from_partition({"u0", "u1"}, {"ghost1", "ghost2"})
    with pytest.raises(FirewallViolation, match="nothing to confirm on"):
        discover_and_confirm(
            _corpus(),
            bad_split,
            discover=lambda c: [_locked_discovery("H1")],
            confirm=lambda h, c: Verdict.supported(h.hypothesis_id, "r"),
            authority=_AUTH,
        )


def test_rejects_discovery_partition_absent_from_corpus():
    # split discovery_ids that don't match any corpus unit -> empty discovery partition ->
    # a hypothesis "discovered" from zero data would launder a hand-authored claim through
    # Firewall B. The discover step must never be called.
    called = {"discover": False}

    def discover(_c):
        called["discover"] = True
        return [_locked_discovery("H1")]

    bad_split = DiscoverConfirmSplit.from_partition({"ghost1", "ghost2"}, {"u3", "u4"})
    with pytest.raises(FirewallViolation, match="nothing to discover from"):
        discover_and_confirm(
            _corpus(),
            bad_split,
            discover=discover,
            confirm=lambda h, c: Verdict.supported(h.hypothesis_id, "r"),
            authority=_AUTH,
        )
    assert called["discover"] is False  # guarded before discovery ran


def test_end_to_end_returns_verdicts():
    verdicts = discover_and_confirm(
        _corpus(),
        _split(),
        discover=lambda c: [_locked_discovery("H1"), _locked_discovery("H2")],
        confirm=lambda h, c: Verdict(h.hypothesis_id, VerdictLabel.SUPPORTED, "r"),
        authority=_AUTH,
    )
    assert [v.hypothesis_id for v in verdicts] == ["H1", "H2"]
    assert all(v.label is VerdictLabel.SUPPORTED for v in verdicts)
