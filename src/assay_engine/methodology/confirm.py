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

import datetime as _dt
import math
from statistics import median
from typing import Iterable, Sequence

from assay_engine.methodology.firewalls import DiscoverConfirmSplit, FirewallViolation
from assay_engine.methodology.hypothesis import Direction, Hypothesis, HypothesisKind
from assay_engine.methodology.preregistration import (
    TimestampAuthority,
    require_preregistered,
)
from assay_engine.methodology.verdict import Verdict


def _gate_preregistration(
    hypothesis: Hypothesis, authority: TimestampAuthority | None
) -> None:
    """Pre-registration gate for the confirm primitives.

    If ``authority`` is supplied, run the full :func:`require_preregistered` check (content
    binding + verifiable timestamp + lock-before-this-moment) — so a study calling a confirm
    primitive *directly* (outside a runner) gets the same guarantee the runners enforce. If it
    is ``None``, fall back to the cheap presence gate (:func:`require_locked`); the caller has
    then opted out of real verification and owns that choice.
    """
    if authority is not None:
        require_preregistered(
            hypothesis, authority=authority, not_after=_dt.datetime.now(tz=_dt.timezone.utc)
        )
    else:
        require_locked(hypothesis)


def require_locked(hypothesis: Hypothesis) -> None:
    """Cheap **presence** gate: refuse a hypothesis that carries no lock fields at all.

    This is defense-in-depth, not the methodology-grade check. It does not verify the proof
    binds the content or that the lock precedes confirmation — that is
    :func:`~assay_engine.methodology.preregistration.require_preregistered`, which the
    confirmatory *runners* (:mod:`adjudication`, :mod:`discovery`) call before they confirm.
    A study driving :func:`confirm_whole_corpus`/:func:`confirm_unit_level` directly (outside a
    runner) should call ``require_preregistered`` itself to get the real guarantee.
    """
    if not hypothesis.locked:
        raise FirewallViolation(
            f"hypothesis {hypothesis.hypothesis_id!r} is not locked; confirm is forbidden "
            "before pre-registration (Firewall B / pre-registration)"
        )


def _validate_alpha(alpha: float) -> None:
    # A significance threshold of 0.5 or more is not a meaningful one-sided level, and
    # admitting it lets both tails register "significant" at once (alpha < 0.5 guarantees
    # p_support + p_contra >= 1 cannot both fall below alpha) — fix-review nit on issue #2.
    if not (0.0 < alpha < 0.5):
        raise ValueError(f"alpha must be in (0, 0.5); got {alpha}")


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
    appropriate to the claim's predicted direction. For a unit-level held-out test the engine
    is handed only an opaque ``statistic`` + ``p_value`` and cannot itself infer whether the
    statistic supports or contradicts the claim — so ``direction_supports_claim`` is a trusted
    caller obligation, ``statistic`` is recorded for provenance only (it does NOT gate the
    verdict), and the deciding flag is recorded in ``evidence`` so the verdict is re-derivable
    (audit pass 2, issue #20). Inputs are validated (issue #4) and the recorded decision rule
    reflects the caller's ``test_description``, not a hard-coded sidedness label (issue #2).
    """
    _validate_pvalue(p_value)
    _validate_alpha(alpha)
    _validate_finite("statistic", statistic)

    rule = f"{test_description} at alpha={alpha}; powered={powered}"
    common = dict(
        statistic=statistic,
        threshold=alpha,
        evidence={"p_value": p_value, "direction_supports_claim": direction_supports_claim},
    )
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
    authority: TimestampAuthority | None = None,
) -> Verdict:
    """Confirm a unit-level hypothesis on the held-out partition only.

    Pass ``authority`` to verify pre-registration in full (content binding + timestamp +
    lock-before-now); omit it to fall back to the presence gate (see :func:`require_locked`).
    """
    if hypothesis.kind is not HypothesisKind.UNIT_LEVEL:
        raise ValueError("confirm_unit_level requires a UNIT_LEVEL hypothesis")
    _gate_preregistration(hypothesis, authority)
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


def _empirical_p(null: Sequence[float], observed: float, tail: Direction) -> float:
    """One-sided empirical p-value with +1 smoothing for the given tail."""
    n = len(null)
    if tail == "greater":
        extreme = sum(1 for v in null if v >= observed)
    else:
        extreme = sum(1 for v in null if v <= observed)
    return (extreme + 1) / (n + 1)


def _resample_stability(
    resamples: Sequence[float], reference: float, tail: Direction
) -> float:
    """Fraction of resampled statistics that fall on the predicted side of ``reference``.

    A measured stand-in for "the effect direction reproduces across resamples": the closer
    to 1.0, the more consistently the resampled statistic stays in the predicted tail.
    """
    if tail == "greater":
        agree = sum(1 for r in resamples if r > reference)
    else:
        agree = sum(1 for r in resamples if r < reference)
    return agree / len(resamples)


def _resolve_direction(
    hypothesis: Hypothesis, predicted_direction: Direction | None
) -> Direction:
    """Direction is fixed at lock time on the hypothesis (issue #24); the confirm-time
    argument is optional and, if given, must match the pre-registered one."""
    locked_dir = hypothesis.predicted_direction
    if locked_dir is not None:
        if predicted_direction is not None and predicted_direction != locked_dir:
            raise ValueError(
                "predicted_direction argument contradicts the hypothesis's pre-registered "
                f"direction ({predicted_direction!r} != {locked_dir!r})"
            )
        return locked_dir
    if predicted_direction is None:
        raise ValueError(
            "no predicted_direction: set it on the hypothesis at pre-registration "
            "(preferred) or pass it explicitly"
        )
    return predicted_direction


def confirm_whole_corpus(
    hypothesis: Hypothesis,
    *,
    observed: float,
    null_distribution: Sequence[float],
    alpha: float,
    resample_statistics: Sequence[float] | None = None,
    stability_threshold: float = 0.9,
    predicted_direction: Direction | None = None,
    authority: TimestampAuthority | None = None,
) -> Verdict:
    """Confirm a whole-corpus hypothesis against a null distribution + measured stability.

    Pass ``authority`` to verify pre-registration in full (content binding + timestamp +
    lock-before-now); omit it to fall back to the presence gate (see :func:`require_locked`).

    The predicted tail is taken from the hypothesis's pre-registered ``predicted_direction``
    (issue #24). The pattern must (a) beat the null at ``alpha`` in the predicted tail and
    (b) be **stable across resamples** — measured by the engine from ``resample_statistics``,
    not asserted by the caller (audit pass 2, issue #21). Outcomes:

    - significant in the predicted tail AND stable → ``supported``;
    - significant in the *opposite* tail → ``contradicted``;
    - unstable, not significant, or stability not assessed → ``indeterminate``.

    If ``resample_statistics`` is omitted, stability cannot be measured, so ``supported`` is
    unavailable and the verdict is ``indeterminate`` ("stability not assessed").
    """
    if hypothesis.kind is not HypothesisKind.WHOLE_CORPUS:
        raise ValueError("confirm_whole_corpus requires a WHOLE_CORPUS hypothesis")
    _gate_preregistration(hypothesis, authority)
    _validate_alpha(alpha)
    _validate_finite("observed", observed)
    if not null_distribution:
        raise ValueError("a null/permutation distribution is required for whole-corpus confirmation")
    for v in null_distribution:
        _validate_finite("null_distribution value", v)
    if not (0.0 < stability_threshold <= 1.0):
        raise ValueError(f"stability_threshold must be in (0, 1]; got {stability_threshold}")

    direction = _resolve_direction(hypothesis, predicted_direction)
    opposite: Direction = "less" if direction == "greater" else "greater"
    p_support = _empirical_p(null_distribution, observed, direction)
    p_contra = _empirical_p(null_distribution, observed, opposite)
    n = len(null_distribution)

    stability: float | None = None
    if resample_statistics is not None:
        if not resample_statistics:
            raise ValueError("resample_statistics, if given, must be non-empty")
        for r in resample_statistics:
            _validate_finite("resample statistic", r)
        stability = _resample_stability(resample_statistics, median(null_distribution), direction)
    stable = stability is not None and stability >= stability_threshold

    rule = (
        f"empirical p from {n}-sample null at alpha={alpha}, predicted tail '{direction}'; "
        f"stability across resamples >= {stability_threshold} (engine-measured)"
    )
    evidence = {
        "p_support": p_support,
        "p_contradict": p_contra,
        "null_n": n,
        "predicted_direction": direction,
        "stability": stability,
        "stability_threshold": stability_threshold,
        "n_resamples": len(resample_statistics) if resample_statistics is not None else 0,
    }
    common = dict(statistic=observed, threshold=alpha, evidence=evidence)

    # A contradiction (significant in the opposite tail) is reportable without stability.
    if p_contra <= alpha:
        return Verdict.contradicted(
            hypothesis.hypothesis_id, rule, notes="significant in the opposite tail", **common
        )
    if stability is None:
        return Verdict.indeterminate(
            hypothesis.hypothesis_id, rule,
            notes="stability not assessed (no resamples supplied)", **common,
        )
    if not stable:
        return Verdict.indeterminate(
            hypothesis.hypothesis_id, rule, notes="unstable across resamples", **common
        )
    if p_support <= alpha:
        return Verdict.supported(hypothesis.hypothesis_id, rule, **common)
    return Verdict.indeterminate(
        hypothesis.hypothesis_id, rule, notes="does not beat null at alpha", **common
    )
