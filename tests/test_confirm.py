"""Confirmatory machinery: locking gate, three-verdict mapping, direction-aware null test,
input validation, and the unit-level path (audit pass 1: #2, #4, #5, #17)."""

import pytest

from assay_engine.methodology.confirm import (
    confirm_unit_level,
    confirm_whole_corpus,
    require_locked,
    verdict_from_pvalue,
)
from assay_engine.methodology.firewalls import DiscoverConfirmSplit, FirewallViolation
from assay_engine.methodology.hypothesis import (
    Hypothesis,
    HypothesisKind,
    HypothesisOrigin,
)
from assay_engine.methodology.verdict import VerdictLabel


def _locked(kind: HypothesisKind, hid: str = "h1") -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hid,
        statement="x",
        kind=kind,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="t",
        decision_rule="r",
        locked_at="2026-06-15T00:00:00Z",
        timestamp_proof="rfc3161:deadbeef",
    )


def _unlocked(kind: HypothesisKind) -> Hypothesis:
    return Hypothesis(
        hypothesis_id="h0",
        statement="x",
        kind=kind,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="t",
        decision_rule="r",
    )


# ---- locking gate ----

def test_require_locked_blocks_unlocked_hypothesis():
    assert not _unlocked(HypothesisKind.WHOLE_CORPUS).locked
    with pytest.raises(FirewallViolation):
        require_locked(_unlocked(HypothesisKind.WHOLE_CORPUS))


# ---- verdict_from_pvalue: three outcomes + validation ----

def test_verdict_mapping_covers_three_outcomes():
    assert verdict_from_pvalue(
        "h", statistic=3.0, p_value=0.01, alpha=0.05, powered=True,
        direction_supports_claim=True,
    ).label is VerdictLabel.SUPPORTED
    assert verdict_from_pvalue(
        "h", statistic=3.0, p_value=0.01, alpha=0.05, powered=True,
        direction_supports_claim=False,
    ).label is VerdictLabel.CONTRADICTED
    assert verdict_from_pvalue(
        "h", statistic=0.1, p_value=0.4, alpha=0.05, powered=False,
        direction_supports_claim=True,
    ).label is VerdictLabel.INDETERMINATE
    assert verdict_from_pvalue(
        "h", statistic=0.1, p_value=0.4, alpha=0.05, powered=True,
        direction_supports_claim=True,
    ).label is VerdictLabel.INDETERMINATE


@pytest.mark.parametrize(
    "kw",
    [
        {"p_value": -0.1},
        {"p_value": 1.5},
        {"alpha": 0.0},
        {"alpha": 1.0},
        {"statistic": float("nan")},
        {"statistic": float("inf")},
    ],
)
def test_verdict_from_pvalue_validates_inputs(kw):
    base = dict(statistic=1.0, p_value=0.01, alpha=0.05, powered=True,
                direction_supports_claim=True)
    base.update(kw)
    with pytest.raises(ValueError):
        verdict_from_pvalue("h", **base)


def test_rule_string_is_not_hardcoded_two_sided():
    v = verdict_from_pvalue(
        "h", statistic=1.0, p_value=0.01, alpha=0.05, powered=True,
        direction_supports_claim=True, test_description="held-out unit-level test",
    )
    assert "two-sided" not in v.decision_rule
    assert "held-out unit-level test" in v.decision_rule


# ---- confirm_whole_corpus: direction-aware (issue #2) ----

def test_whole_corpus_supported_upper_tail():
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS), observed=10.0,
        null_distribution=[0.0] * 100, alpha=0.05,
        stable_across_resamples=True, predicted_direction="greater",
    )
    assert v.label is VerdictLabel.SUPPORTED


def test_whole_corpus_supported_lower_tail():
    # A claim predicting a LOW statistic, observed far below the null, must be SUPPORTED
    # (previously returned INDETERMINATE under direction-blind upper-tail-only logic).
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS), observed=0.0,
        null_distribution=[10.0] * 100, alpha=0.05,
        stable_across_resamples=True, predicted_direction="less",
    )
    assert v.label is VerdictLabel.SUPPORTED


def test_whole_corpus_contradicted_when_significant_in_opposite_tail():
    # Claim predicts HIGH, but observed is far below the null -> a real contradiction.
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS), observed=0.0,
        null_distribution=[10.0] * 100, alpha=0.05,
        stable_across_resamples=True, predicted_direction="greater",
    )
    assert v.label is VerdictLabel.CONTRADICTED


def test_whole_corpus_not_significant_is_indeterminate():
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS), observed=5.0,
        null_distribution=list(range(100)), alpha=0.01,
        stable_across_resamples=True, predicted_direction="greater",
    )
    assert v.label is VerdictLabel.INDETERMINATE


def test_whole_corpus_unstable_is_indeterminate_even_if_beats_null():
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS), observed=10.0,
        null_distribution=[0.0] * 100, alpha=0.05,
        stable_across_resamples=False, predicted_direction="greater",
    )
    assert v.is_indeterminate


def test_whole_corpus_requires_null_distribution():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS), observed=1.0,
            null_distribution=[], alpha=0.05,
            stable_across_resamples=True, predicted_direction="greater",
        )


def test_whole_corpus_rejects_non_finite():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS), observed=float("nan"),
            null_distribution=[1.0, 2.0], alpha=0.05,
            stable_across_resamples=True, predicted_direction="greater",
        )
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS), observed=1.0,
            null_distribution=[1.0, float("inf")], alpha=0.05,
            stable_across_resamples=True, predicted_direction="greater",
        )


def test_whole_corpus_wrong_kind_rejected():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.UNIT_LEVEL), observed=1.0,
            null_distribution=[0.0], alpha=0.05,
            stable_across_resamples=True, predicted_direction="greater",
        )


def test_whole_corpus_unlocked_rejected():
    with pytest.raises(FirewallViolation):
        confirm_whole_corpus(
            _unlocked(HypothesisKind.WHOLE_CORPUS), observed=1.0,
            null_distribution=[0.0], alpha=0.05,
            stable_across_resamples=True, predicted_direction="greater",
        )


# ---- confirm_unit_level (issue #5, #17) ----

def _split() -> DiscoverConfirmSplit:
    return DiscoverConfirmSplit.from_partition({"a", "b"}, {"c", "d"})


def test_unit_level_clean_verdict():
    v = confirm_unit_level(
        _locked(HypothesisKind.UNIT_LEVEL), split=_split(), evaluated_ids={"c", "d"},
        statistic=2.0, p_value=0.01, alpha=0.05, powered=True,
        direction_supports_claim=True,
    )
    assert v.label is VerdictLabel.SUPPORTED


def test_unit_level_wrong_kind_rejected():
    with pytest.raises(ValueError):
        confirm_unit_level(
            _locked(HypothesisKind.WHOLE_CORPUS), split=_split(), evaluated_ids={"c"},
            statistic=2.0, p_value=0.01, alpha=0.05, powered=True,
            direction_supports_claim=True,
        )


def test_unit_level_unlocked_rejected():
    with pytest.raises(FirewallViolation):
        confirm_unit_level(
            _unlocked(HypothesisKind.UNIT_LEVEL), split=_split(), evaluated_ids={"c"},
            statistic=2.0, p_value=0.01, alpha=0.05, powered=True,
            direction_supports_claim=True,
        )


def test_unit_level_rejects_discovery_id_leak():
    with pytest.raises(FirewallViolation):
        confirm_unit_level(
            _locked(HypothesisKind.UNIT_LEVEL), split=_split(), evaluated_ids={"a"},
            statistic=2.0, p_value=0.01, alpha=0.05, powered=True,
            direction_supports_claim=True,
        )


def test_unit_level_rejects_empty_evaluated_ids():
    with pytest.raises(FirewallViolation):
        confirm_unit_level(
            _locked(HypothesisKind.UNIT_LEVEL), split=_split(), evaluated_ids=set(),
            statistic=2.0, p_value=0.01, alpha=0.05, powered=True,
            direction_supports_claim=True,
        )
