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


def _locked(kind: HypothesisKind, hid: str = "h1", predicted_direction=None) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hid,
        statement="x",
        kind=kind,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="t",
        decision_rule="r",
        locked_at="2026-06-15T00:00:00Z",
        timestamp_proof="rfc3161:deadbeef",
        predicted_direction=predicted_direction,
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
    assert (
        verdict_from_pvalue(
            "h",
            statistic=3.0,
            p_value=0.01,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        ).label
        is VerdictLabel.SUPPORTED
    )
    assert (
        verdict_from_pvalue(
            "h",
            statistic=3.0,
            p_value=0.01,
            alpha=0.05,
            powered=True,
            direction_supports_claim=False,
        ).label
        is VerdictLabel.CONTRADICTED
    )
    assert (
        verdict_from_pvalue(
            "h",
            statistic=0.1,
            p_value=0.4,
            alpha=0.05,
            powered=False,
            direction_supports_claim=True,
        ).label
        is VerdictLabel.INDETERMINATE
    )
    assert (
        verdict_from_pvalue(
            "h",
            statistic=0.1,
            p_value=0.4,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        ).label
        is VerdictLabel.INDETERMINATE
    )


def test_verdict_pvalue_boundary_is_inclusive_at_alpha():
    # #142: p_value exactly == alpha is significant (the documented `<= alpha` rule). Pins the
    # inclusive boundary; flipping to `< alpha` would make this CONTRADICTED/INDETERMINATE.
    assert (
        verdict_from_pvalue(
            "h",
            statistic=2.0,
            p_value=0.05,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        ).label
        is VerdictLabel.SUPPORTED
    )
    assert (
        verdict_from_pvalue(
            "h",
            statistic=2.0,
            p_value=0.05,
            alpha=0.05,
            powered=True,
            direction_supports_claim=False,
        ).label
        is VerdictLabel.CONTRADICTED
    )


@pytest.mark.parametrize(
    "kw",
    [
        {"p_value": -0.1},
        {"p_value": 1.5},
        {"alpha": 0.0},
        {"alpha": 0.5},
        {"alpha": 1.0},
        {"statistic": float("nan")},
        {"statistic": float("inf")},
    ],
)
def test_verdict_from_pvalue_validates_inputs(kw):
    base = dict(
        statistic=1.0, p_value=0.01, alpha=0.05, powered=True, direction_supports_claim=True
    )
    base.update(kw)
    with pytest.raises(ValueError):
        verdict_from_pvalue("h", **base)


def test_rule_string_is_not_hardcoded_two_sided():
    v = verdict_from_pvalue(
        "h",
        statistic=1.0,
        p_value=0.01,
        alpha=0.05,
        powered=True,
        direction_supports_claim=True,
        test_description="held-out unit-level test",
    )
    assert "two-sided" not in v.decision_rule
    assert "held-out unit-level test" in v.decision_rule


# ---- confirm_whole_corpus: direction-aware (#2) + engine-measured stability (#21) ----

_STABLE_HI = [100.0] * 20  # resamples far above any small null -> stable for "greater"
_STABLE_LO = [-100.0] * 20  # far below -> stable for "less"


def test_whole_corpus_rejects_invalid_predicted_direction():
    # #128 + #F-002: an unrecognized direction must RAISE, not silently fall through to the
    # 'less' tail (which would flip supported<->contradicted). A locked invalid direction is now
    # rejected at the EARLIEST point — hypothesis construction — so it can never be bound into a
    # pre-registration proof; the confirm-time-argument path still validates too.
    with pytest.raises(ValueError, match="predicted_direction must be 'greater' or 'less'"):
        _locked(HypothesisKind.WHOLE_CORPUS, predicted_direction="up")
    ok = _locked(HypothesisKind.WHOLE_CORPUS)  # no locked direction
    with pytest.raises(ValueError, match="predicted_direction must be one of"):
        confirm_whole_corpus(
            ok,
            observed=10.0,
            null_distribution=[0.0] * 100,
            alpha=0.05,
            predicted_direction="sideways",
        )


def test_whole_corpus_stability_requires_reproducing_the_observed_effect():
    # #139: resamples that clear the null median by an epsilon (reproducing only the effect SIGN,
    # not its magnitude) must NOT earn stability=1.0 / SUPPORTED. Stability must measure that each
    # resample, scored against the null, is itself significant in the predicted tail.
    null = list(range(0, 21))  # median 10
    barely = [10.0001] * 100  # just above the null median, far below the observed effect of 100
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=100.0,
        null_distribution=null,
        alpha=0.05,
        resample_statistics=barely,
        predicted_direction="greater",
    )
    assert v.label is VerdictLabel.INDETERMINATE  # pre-fix: SUPPORTED with stability=1.0
    assert v.evidence["stability"] == 0.0  # no resample reproduces the observed effect
    # a genuinely reproducing resample distribution (each significant vs the null) is still stable
    strong = [100.0] * 100
    v2 = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=100.0,
        null_distribution=null,
        alpha=0.05,
        resample_statistics=strong,
        predicted_direction="greater",
    )
    assert v2.label is VerdictLabel.SUPPORTED and v2.evidence["stability"] == 1.0


def test_whole_corpus_supported_upper_tail():
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=10.0,
        null_distribution=[0.0] * 100,
        alpha=0.05,
        resample_statistics=_STABLE_HI,
        predicted_direction="greater",
    )
    assert v.label is VerdictLabel.SUPPORTED
    assert v.evidence["stability"] == 1.0  # engine-measured, not asserted (#21)


def test_whole_corpus_supported_lower_tail():
    # A claim predicting a LOW statistic, observed far below the null, must be SUPPORTED
    # (previously returned INDETERMINATE under direction-blind upper-tail-only logic).
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=0.0,
        null_distribution=[10.0] * 100,
        alpha=0.05,
        resample_statistics=_STABLE_LO,
        predicted_direction="less",
    )
    assert v.label is VerdictLabel.SUPPORTED


def test_whole_corpus_contradicted_when_significant_in_opposite_tail():
    # Claim predicts HIGH, but observed is far below the null -> a real contradiction
    # (reportable without resamples; a contradiction does not need stability).
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=0.0,
        null_distribution=[10.0] * 100,
        alpha=0.05,
        predicted_direction="greater",
    )
    assert v.label is VerdictLabel.CONTRADICTED


def test_whole_corpus_stability_not_assessed_without_resamples():
    # issue #21: SUPPORTED is unavailable if stability was never measured.
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=10.0,
        null_distribution=[0.0] * 100,
        alpha=0.05,
        predicted_direction="greater",
    )
    assert v.label is VerdictLabel.INDETERMINATE
    assert v.evidence["stability"] is None


def test_whole_corpus_unstable_resamples_is_indeterminate_even_if_beats_null():
    # issue #21: resamples that don't reproduce the direction -> not stable -> indeterminate.
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=10.0,
        null_distribution=[0.0] * 100,
        alpha=0.05,
        resample_statistics=[-1.0] * 20,
        predicted_direction="greater",
    )
    assert v.is_indeterminate
    assert v.evidence["stability"] == 0.0


def test_whole_corpus_not_significant_is_indeterminate():
    v = confirm_whole_corpus(
        _locked(HypothesisKind.WHOLE_CORPUS),
        observed=5.0,
        null_distribution=list(range(100)),
        alpha=0.01,
        resample_statistics=_STABLE_HI,
        predicted_direction="greater",
    )
    assert v.label is VerdictLabel.INDETERMINATE


def test_whole_corpus_uses_pre_registered_direction():
    # issue #24: direction fixed on the locked hypothesis; no confirm-time arg needed.
    h = _locked(HypothesisKind.WHOLE_CORPUS, predicted_direction="less")
    v = confirm_whole_corpus(
        h,
        observed=0.0,
        null_distribution=[10.0] * 100,
        alpha=0.05,
        resample_statistics=_STABLE_LO,
    )
    assert v.label is VerdictLabel.SUPPORTED


def test_whole_corpus_rejects_direction_conflict_with_lock():
    # issue #24: a confirm-time direction contradicting the pre-registered one is refused.
    h = _locked(HypothesisKind.WHOLE_CORPUS, predicted_direction="less")
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            h,
            observed=0.0,
            null_distribution=[10.0] * 100,
            alpha=0.05,
            resample_statistics=_STABLE_LO,
            predicted_direction="greater",
        )


def test_whole_corpus_requires_some_direction():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS),
            observed=0.0,
            null_distribution=[10.0] * 100,
            alpha=0.05,
            resample_statistics=_STABLE_LO,
        )


def test_whole_corpus_rejects_bad_stability_threshold():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS),
            observed=1.0,
            null_distribution=[0.0],
            alpha=0.05,
            predicted_direction="greater",
            stability_threshold=1.5,
        )


def test_whole_corpus_rejects_empty_resamples():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS),
            observed=1.0,
            null_distribution=[0.0],
            alpha=0.05,
            predicted_direction="greater",
            resample_statistics=[],
        )


def test_whole_corpus_rejects_nonfinite_resample():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS),
            observed=1.0,
            null_distribution=[0.0],
            alpha=0.05,
            predicted_direction="greater",
            resample_statistics=[float("nan")],
        )


def test_whole_corpus_requires_null_distribution():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS),
            observed=1.0,
            null_distribution=[],
            alpha=0.05,
            predicted_direction="greater",
        )


def test_whole_corpus_rejects_non_finite():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS),
            observed=float("nan"),
            null_distribution=[1.0, 2.0],
            alpha=0.05,
            predicted_direction="greater",
        )
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.WHOLE_CORPUS),
            observed=1.0,
            null_distribution=[1.0, float("inf")],
            alpha=0.05,
            predicted_direction="greater",
        )


def test_whole_corpus_wrong_kind_rejected():
    with pytest.raises(ValueError):
        confirm_whole_corpus(
            _locked(HypothesisKind.UNIT_LEVEL),
            observed=1.0,
            null_distribution=[0.0],
            alpha=0.05,
            predicted_direction="greater",
        )


def test_whole_corpus_unlocked_rejected():
    with pytest.raises(FirewallViolation):
        confirm_whole_corpus(
            _unlocked(HypothesisKind.WHOLE_CORPUS),
            observed=1.0,
            null_distribution=[0.0],
            alpha=0.05,
            predicted_direction="greater",
        )


# ---- confirm_unit_level (issue #5, #17) ----


def _split() -> DiscoverConfirmSplit:
    return DiscoverConfirmSplit.from_partition({"a", "b"}, {"c", "d"})


def test_unit_level_clean_verdict():
    v = confirm_unit_level(
        _locked(HypothesisKind.UNIT_LEVEL),
        split=_split(),
        evaluated_ids={"c", "d"},
        statistic=2.0,
        p_value=0.01,
        alpha=0.05,
        powered=True,
        direction_supports_claim=True,
    )
    assert v.label is VerdictLabel.SUPPORTED
    # issue #20: the deciding direction flag is recorded so the verdict is re-derivable
    assert v.evidence["direction_supports_claim"] is True


def test_unit_level_wrong_kind_rejected():
    with pytest.raises(ValueError):
        confirm_unit_level(
            _locked(HypothesisKind.WHOLE_CORPUS),
            split=_split(),
            evaluated_ids={"c"},
            statistic=2.0,
            p_value=0.01,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        )


def test_unit_level_unlocked_rejected():
    with pytest.raises(FirewallViolation):
        confirm_unit_level(
            _unlocked(HypothesisKind.UNIT_LEVEL),
            split=_split(),
            evaluated_ids={"c"},
            statistic=2.0,
            p_value=0.01,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        )


def test_unit_level_rejects_discovery_id_leak():
    with pytest.raises(FirewallViolation):
        confirm_unit_level(
            _locked(HypothesisKind.UNIT_LEVEL),
            split=_split(),
            evaluated_ids={"a"},
            statistic=2.0,
            p_value=0.01,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        )


def test_unit_level_rejects_empty_evaluated_ids():
    with pytest.raises(FirewallViolation):
        confirm_unit_level(
            _locked(HypothesisKind.UNIT_LEVEL),
            split=_split(),
            evaluated_ids=set(),
            statistic=2.0,
            p_value=0.01,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        )


# ---- predicted_direction validation at the earliest point (#F-002) ----


def test_hypothesis_rejects_invalid_predicted_direction_at_construction():
    # #F-002: an invalid direction must be rejected at hypothesis construction — the earliest
    # point — so it can never be cryptographically bound into a pre-registration proof, nor reach
    # confirm_unit_level (which takes direction as a trusted caller flag and otherwise never
    # checks the locked direction at all). Pre-fix: construction accepted "UP" silently.
    with pytest.raises(ValueError, match="predicted_direction must be 'greater' or 'less'"):
        Hypothesis(
            hypothesis_id="h",
            statement="s",
            kind=HypothesisKind.UNIT_LEVEL,
            origin=HypothesisOrigin.DISCOVERY,
            test_name="t",
            decision_rule="r",
            predicted_direction="UP",
        )


def test_confirm_unit_level_revalidates_locked_direction_defensively():
    # #F-002 defense-in-depth: even if an invalid predicted_direction is smuggled onto a
    # hypothesis past __post_init__, confirm_unit_level re-validates rather than confirming
    # against an unrecognized tail. Pre-fix: confirm_unit_level never read predicted_direction.
    h = _locked(HypothesisKind.UNIT_LEVEL, predicted_direction="greater")
    object.__setattr__(h, "predicted_direction", "UP")  # bypass construction-time validation
    with pytest.raises(ValueError, match="predicted_direction must be one of"):
        confirm_unit_level(
            h,
            split=_split(),
            evaluated_ids={"c", "d"},
            statistic=2.0,
            p_value=0.01,
            alpha=0.05,
            powered=True,
            direction_supports_claim=True,
        )
