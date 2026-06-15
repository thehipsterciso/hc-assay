"""Confirmatory-test machinery (METHODOLOGY.md §2, §4).

A confirmatory test takes a *locked* hypothesis and returns a :class:`Verdict`. Two
mechanisms, selected by hypothesis kind:

- unit-level → evaluate on a held-out confirmation partition (Firewall B via
  :class:`DiscoverConfirmSplit`);
- whole-corpus → compare the observed statistic against a null/permutation distribution and
  require stability across resamples.

This module defines the *contract and guards* around confirmation. The concrete statistics
are supplied by callers via the baseline toolkit; the engine's responsibility here is to
refuse to confirm an unlocked hypothesis or on discovery data, validate the supplied
statistics, and map an outcome onto one of the three verdicts honestly (including
``indeterminate``).

Direction handling (audit pass 1, issue #2): a claim predicts the statistic lies in a
particular tail of the null. The empirical p-value is computed against *that* tail, so a
claim predicting a low value is confirmable, and a genuine contradiction (significant in the
opposite tail) is detectable — both were impossible under the previous direction-blind
upper-tail-only implementation.
"""

from __future__ import annotations

import math
from typing import Iterable, Literal

from assay_engine.methodology.firewalls import DiscoverConfirmSplit, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind
from assay_engine.methodology.verdict import Verdict

Direction = Literal["greater", "less"]


def require_locked(hypothesis: Hypothesis) -> None:
    """Gate: a hypothesis must be locked + timestamped before any confirmatory step."""
    if not hypothesis.locked:
        raise FirewallViolation(
            f"hypothesis {hypothesis.hypothesis_id!r} is not locked; confirm is forbidden "
            "before pre-registration (Firewall B / pre-registration)"
        )


def _validate_alpha(alpha: float) -> None:
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")


def _validate_pvalue(p_value: float) -> None:
    if not (0.0 <= p_value <= 1.0):
        raise ValueError(f"p_value must be in [0, 1]; got {p_value}")


def _validate_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number; got {value}")


def verdict_from_pvalue(
    hypothesis_id: str,
    *,
    statistic: float,
    p_value: float,
    alpha: float,
    powered: bool,
    direction_supports_claim: bool,
    test_description: str = "confirmatory test",
) -> Verdict:
    """Map a confirmatory statistic onto the three verdicts.

    - not ``powered`` → ``indeterminate`` (the method cannot decide).
    - significant and direction agrees with the claim → ``supported``.
    - significant and direction disagrees → ``contradicted``.
    - not significant → ``indeterminate`` (absence of evidence is not contradiction here).

    ``p_value`` and ``direction_supports_claim`` must be derived by the caller from a test
    appropriate to the claim's predicted direction. Inputs are validated (issue #4) and the
    recorded decision rule reflects the caller's ``test_description`` rather than a hard-coded
    (and previously incorrect) sidedness label (issue #2).
    """
    _validate_pvalue(p_value)
    _validate_alpha(alpha)
    _validate_finite("statistic", statistic)

    rule = f"{test_description} at alpha={alpha}; powered={powered}"
    common = dict(statistic=statistic, threshold=alpha, evidence={"p_value": p_value})
    if not powered:
        return Verdict.indeterminate(hypothesis_id, rule, notes="underpowered", **common)
    if p_value <= alpha:
        if direction_supports_claim:
            return Verdict.supported(hypothesis_id, rule, **common)
        return Verdict.contradicted(hypothesis_id, rule, **common)
    return Verdict.indeterminate(
        hypothesis_id, rule, notes="not significant at alpha", **common
    )


def confirm_unit_level(
    hypothesis: Hypothesis,
    *,
    split: DiscoverConfirmSplit,
    evaluated_ids: Iterable[str],
    statistic: float,
    p_value: float,
    alpha: float,
    powered: bool,
    direction_supports_claim: bool,
) -> Verdict:
    """Confirm a unit-level hypothesis on the held-out partition only."""
    if hypothesis.kind is not HypothesisKind.UNIT_LEVEL:
        raise ValueError("confirm_unit_level requires a UNIT_LEVEL hypothesis")
    require_locked(hypothesis)
    split.assert_confirm_only(evaluated_ids)  # Firewall B (rejects empty / discovery ids)
    return verdict_from_pvalue(
        hypothesis.hypothesis_id,
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        powered=powered,
        direction_supports_claim=direction_supports_claim,
        test_description="held-out unit-level test",
    )


def _empirical_p(null: list[float], observed: float, tail: Direction) -> float:
    """One-sided empirical p-value with +1 smoothing for the given tail."""
    n = len(null)
    if tail == "greater":
        extreme = sum(1 for v in null if v >= observed)
    else:
        extreme = sum(1 for v in null if v <= observed)
    return (extreme + 1) / (n + 1)


def confirm_whole_corpus(
    hypothesis: Hypothesis,
    *,
    observed: float,
    null_distribution: list[float],
    alpha: float,
    stable_across_resamples: bool,
    predicted_direction: Direction,
) -> Verdict:
    """Confirm a whole-corpus hypothesis against a null distribution + stability check.

    ``predicted_direction`` is the tail the claim predicts the observed statistic lies in
    (``"greater"`` or ``"less"`` than the null). The pattern must (a) beat the null at
    ``alpha`` in the predicted tail and (b) be stable across resamples → ``supported``. A
    result significant in the *opposite* tail → ``contradicted``. Anything else (unstable,
    or not significant in either tail) → ``indeterminate``.
    """
    if hypothesis.kind is not HypothesisKind.WHOLE_CORPUS:
        raise ValueError("confirm_whole_corpus requires a WHOLE_CORPUS hypothesis")
    require_locked(hypothesis)
    _validate_alpha(alpha)
    _validate_finite("observed", observed)
    if not null_distribution:
        raise ValueError("a null/permutation distribution is required for whole-corpus confirmation")
    for v in null_distribution:
        _validate_finite("null_distribution value", v)

    opposite: Direction = "less" if predicted_direction == "greater" else "greater"
    p_support = _empirical_p(null_distribution, observed, predicted_direction)
    p_contra = _empirical_p(null_distribution, observed, opposite)
    n = len(null_distribution)
    rule = (
        f"empirical p from {n}-sample null at alpha={alpha}, predicted tail "
        f"'{predicted_direction}'; requires stability across resamples"
    )
    evidence = {
        "p_support": p_support,
        "p_contradict": p_contra,
        "null_n": n,
        "stable": stable_across_resamples,
        "predicted_direction": predicted_direction,
    }
    common = dict(statistic=observed, threshold=alpha, evidence=evidence)

    if not stable_across_resamples:
        return Verdict.indeterminate(
            hypothesis.hypothesis_id, rule, notes="unstable across resamples", **common
        )
    if p_support <= alpha:
        return Verdict.supported(hypothesis.hypothesis_id, rule, **common)
    if p_contra <= alpha:
        return Verdict.contradicted(
            hypothesis.hypothesis_id,
            rule,
            notes="significant in the opposite tail",
            **common,
        )
    return Verdict.indeterminate(
        hypothesis.hypothesis_id, rule, notes="does not beat null at alpha", **common
    )
