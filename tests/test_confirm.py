"""Confirmatory machinery: locking gate, three-verdict mapping, whole-corpus null test."""

import pytest

from assay_engine.methodology.confirm import (
    confirm_whole_corpus,
    require_locked,
    verdict_from_pvalue,
)
from assay_engine.methodology.firewalls import FirewallViolation
from assay_engine.methodology.hypothesis import (
    Hypothesis,
    HypothesisKind,
    HypothesisOrigin,
)
from assay_engine.methodology.verdict import VerdictLabel


def _locked_whole_corpus() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="h1",
        statement="global structure exceeds chance",
        kind=HypothesisKind.WHOLE_CORPUS,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="permutation",
        decision_rule="empirical p <= 0.05 and stable",
        locked_at="2026-06-15T00:00:00Z",
        timestamp_proof="rfc3161:deadbeef",
    )


def test_require_locked_blocks_unlocked_hypothesis():
    h = Hypothesis(
        hypothesis_id="h0",
        statement="x",
        kind=HypothesisKind.WHOLE_CORPUS,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="permutation",
        decision_rule="p<=.05",
    )
    assert not h.locked
    with pytest.raises(FirewallViolation):
        require_locked(h)


def test_verdict_mapping_covers_three_outcomes():
    supported = verdict_from_pvalue(
        "h", statistic=3.0, p_value=0.01, alpha=0.05, powered=True,
        direction_supports_claim=True,
    )
    contradicted = verdict_from_pvalue(
        "h", statistic=3.0, p_value=0.01, alpha=0.05, powered=True,
        direction_supports_claim=False,
    )
    underpowered = verdict_from_pvalue(
        "h", statistic=0.1, p_value=0.4, alpha=0.05, powered=False,
        direction_supports_claim=True,
    )
    not_sig = verdict_from_pvalue(
        "h", statistic=0.1, p_value=0.4, alpha=0.05, powered=True,
        direction_supports_claim=True,
    )
    assert supported.label is VerdictLabel.SUPPORTED
    assert contradicted.label is VerdictLabel.CONTRADICTED
    assert underpowered.label is VerdictLabel.INDETERMINATE
    assert not_sig.label is VerdictLabel.INDETERMINATE


def test_whole_corpus_unstable_is_indeterminate_even_if_beats_null():
    h = _locked_whole_corpus()
    null = [0.0] * 100
    v = confirm_whole_corpus(
        h, observed=10.0, null_distribution=null, alpha=0.05,
        stable_across_resamples=False, direction_supports_claim=True,
    )
    assert v.is_indeterminate


def test_whole_corpus_supported_when_beats_null_and_stable():
    h = _locked_whole_corpus()
    null = [0.0] * 100
    v = confirm_whole_corpus(
        h, observed=10.0, null_distribution=null, alpha=0.05,
        stable_across_resamples=True, direction_supports_claim=True,
    )
    assert v.label is VerdictLabel.SUPPORTED


def test_whole_corpus_requires_null_distribution():
    h = _locked_whole_corpus()
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            h, observed=1.0, null_distribution=[], alpha=0.05,
            stable_across_resamples=True, direction_supports_claim=True,
        )
