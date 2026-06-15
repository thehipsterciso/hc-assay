"""Confirmatory-test machinery (METHODOLOGY.md §2, §4).

A confirmatory test takes a *locked* hypothesis and returns a :class:`Verdict`. Two
mechanisms, selected by hypothesis kind:

- unit-level → evaluate on a held-out confirmation partition (Firewall B via
  :class:`DiscoverConfirmSplit`);
- whole-corpus → compare the observed statistic against a null/permutation distribution and
  require stability across resamples.

This module defines the *contract and guards* around confirmation. The concrete statistics
are supplied by callers via the baseline toolkit; the engine's responsibility here is to
refuse to confirm an unlocked hypothesis or on discovery data, and to map an outcome onto
one of the three verdicts honestly (including ``indeterminate``).
"""

from __future__ import annotations

from typing import Iterable

from assay_engine.methodology.firewalls import DiscoverConfirmSplit, FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind
from assay_engine.methodology.verdict import Verdict, VerdictLabel


def require_locked(hypothesis: Hypothesis) -> None:
    """Gate: a hypothesis must be locked + timestamped before any confirmatory step."""
    if not hypothesis.locked:
        raise FirewallViolation(
            f"hypothesis {hypothesis.hypothesis_id!r} is not locked; confirm is forbidden "
            "before pre-registration (Firewall B / pre-registration)"
        )


def verdict_from_pvalue(
    hypothesis_id: str,
    *,
    statistic: float,
    p_value: float,
    alpha: float,
    powered: bool,
    direction_supports_claim: bool,
) -> Verdict:
    """Map a confirmatory statistic onto the three verdicts.

    - not ``powered`` → ``indeterminate`` (the method cannot decide).
    - significant and direction agrees with the claim → ``supported``.
    - significant and direction disagrees → ``contradicted``.
    - not significant → ``indeterminate`` (absence of evidence is not contradiction here;
      a stronger contradiction needs an equivalence/severity test, handled by callers).
    """
    rule = f"two-sided test at alpha={alpha}; powered={powered}"
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
    split.assert_confirm_only(evaluated_ids)  # Firewall B
    return verdict_from_pvalue(
        hypothesis.hypothesis_id,
        statistic=statistic,
        p_value=p_value,
        alpha=alpha,
        powered=powered,
        direction_supports_claim=direction_supports_claim,
    )


def confirm_whole_corpus(
    hypothesis: Hypothesis,
    *,
    observed: float,
    null_distribution: list[float],
    alpha: float,
    stable_across_resamples: bool,
    direction_supports_claim: bool,
) -> Verdict:
    """Confirm a whole-corpus hypothesis against a null distribution + stability check.

    The pattern must (a) beat the permutation/null distribution at ``alpha`` and (b) be
    stable across resamples. Failing stability yields ``indeterminate`` even if the point
    estimate beats the null — an unstable effect is not confirmable.
    """
    if hypothesis.kind is not HypothesisKind.WHOLE_CORPUS:
        raise ValueError("confirm_whole_corpus requires a WHOLE_CORPUS hypothesis")
    require_locked(hypothesis)
    if not null_distribution:
        raise ValueError("a null/permutation distribution is required for whole-corpus confirmation")

    n = len(null_distribution)
    # one-sided empirical p-value (proportion of null at least as extreme), with +1 smoothing
    at_least_as_extreme = sum(1 for v in null_distribution if v >= observed)
    p_value = (at_least_as_extreme + 1) / (n + 1)
    rule = (
        f"empirical p from {n}-sample null at alpha={alpha}; "
        "requires stability across resamples"
    )
    common = dict(
        statistic=observed,
        threshold=alpha,
        evidence={"p_value": p_value, "null_n": n, "stable": stable_across_resamples},
    )
    if not stable_across_resamples:
        return Verdict.indeterminate(
            hypothesis.hypothesis_id, rule, notes="unstable across resamples", **common
        )
    if p_value <= alpha:
        label = (
            VerdictLabel.SUPPORTED if direction_supports_claim else VerdictLabel.CONTRADICTED
        )
        return Verdict(
            hypothesis.hypothesis_id,
            label,
            rule,
            statistic=observed,
            threshold=alpha,
            evidence={"p_value": p_value, "null_n": n, "stable": stable_across_resamples},
        )
    return Verdict.indeterminate(
        hypothesis.hypothesis_id, rule, notes="does not beat null at alpha", **common
    )
