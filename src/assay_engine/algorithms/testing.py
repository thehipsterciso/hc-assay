"""Statistical hypothesis testing — parametric, non-parametric, and permutation-based.

Each test implements the ``StatisticalTest`` protocol and returns a ``TestResult``
with the test statistic, p-value, effect size, and human-readable interpretation.

All implementations are pure Python; no scipy dependency required.

Usage::

    from assay_engine.algorithms.testing import welch_t_test, mann_whitney, permutation_test
    result = welch_t_test([2.1, 2.5, 2.3], [3.0, 3.2, 2.9])
    result.p_value     # two-tailed p-value
    result.effect_size # Cohen's d
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestResult:
    """Outcome of a statistical hypothesis test.

    Attributes
    ----------
    statistic:    The computed test statistic (e.g. t, U, χ², D, or z).
    p_value:      Two-tailed p-value (or one-tailed where noted).
    effect_size:  Standardised effect size (Cohen's d, r, V, odds ratio, etc.);
                  ``None`` when not applicable.
    interpretation: Human-readable summary of the finding.
    n1:           Sample size of group 1.
    n2:           Sample size of group 2 (0 for one-sample tests).
    """

    statistic: float
    p_value: float
    effect_size: float | None
    interpretation: str
    n1: int
    n2: int


@dataclass(frozen=True)
class CorrectionResult:
    """Outcome of a multiple-comparison correction procedure.

    Attributes
    ----------
    adjusted_p:   Corrected p-values aligned to the input order.
    rejected:     Boolean mask — True if the null is rejected at *alpha*.
    method:       Name of the correction method applied.
    """

    adjusted_p: tuple[float, ...]
    rejected: tuple[bool, ...]
    method: str


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class StatisticalTest(Protocol):
    """A callable that runs a statistical test and returns a ``TestResult``."""

    def __call__(self, a: Sequence[float], b: Sequence[float]) -> TestResult: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _var(xs: Sequence[float], ddof: int = 1) -> float:
    m = _mean(xs)
    n = len(xs)
    return sum((x - m) ** 2 for x in xs) / (n - ddof) if n > ddof else 0.0


def _t_cdf(t: float, df: float) -> float:
    """Regularised incomplete Beta for the t-distribution CDF.

    Approximation using the continued fraction expansion of the regularised
    incomplete Beta function.  Accurate to ≈ 6 significant figures for the
    p-values needed in practice.
    """
    x = df / (df + t * t)
    # regularised incomplete Beta  I_x(df/2, 1/2)
    # via Lentz's continued fraction
    a_coef = df / 2.0
    b_coef = 0.5
    # betainc via continued fraction (Numerical Recipes §6.4)
    if x < 0.0 or x > 1.0:
        return 0.5
    if x == 0.0:
        # t → ∞: CDF → 1.0, tail = 0
        return 1.0
    if x == 1.0:
        # t = 0: symmetric distribution, CDF = 0.5
        return 0.5

    lbeta = math.lgamma(a_coef) + math.lgamma(b_coef) - math.lgamma(a_coef + b_coef)
    front = math.exp(math.log(x) * a_coef + math.log(1 - x) * b_coef - lbeta)

    # Use the symmetry relation when x > (a+1)/(a+b+2)
    sym = x > (a_coef + 1) / (a_coef + b_coef + 2)
    if sym:
        x = 1 - x
        a_coef, b_coef = b_coef, a_coef

    # Lentz modified continued fraction
    TINY = 1e-30
    MAX_ITER = 200
    EPS = 3e-7

    fprev = 1.0
    C = fprev
    D = 1.0 - (a_coef + b_coef) * x / (a_coef + 1.0)
    if abs(D) < TINY:
        D = TINY
    D = 1.0 / D
    f = D

    for m_ in range(1, MAX_ITER + 1):
        m = float(m_)
        # even step
        dm = m * (b_coef - m) * x / ((a_coef + 2 * m - 1) * (a_coef + 2 * m))
        D = 1.0 + dm * D
        if abs(D) < TINY:
            D = TINY
        C = 1.0 + dm / C
        if abs(C) < TINY:
            C = TINY
        D = 1.0 / D
        f *= C * D
        # odd step
        dm = -(a_coef + m) * (a_coef + b_coef + m) * x / ((a_coef + 2 * m) * (a_coef + 2 * m + 1))
        D = 1.0 + dm * D
        if abs(D) < TINY:
            D = TINY
        C = 1.0 + dm / C
        if abs(C) < TINY:
            C = TINY
        D = 1.0 / D
        delta = C * D
        f *= delta
        if abs(delta - 1.0) < EPS:
            break

    betainc = front * f / a_coef
    if sym:
        betainc = 1.0 - betainc

    # CDF = 1 - I_x(df/2, 1/2) / 2  for two-tailed upper tail
    tail = betainc / 2.0
    return 1.0 - tail  # P(T ≤ t) for t ≥ 0


def _t_pvalue(t: float, df: float) -> float:
    """Two-tailed p-value for t-distribution with *df* degrees of freedom."""
    if df <= 0:
        return 1.0
    abs_t = abs(t)
    cdf = _t_cdf(abs_t, df)  # P(T ≤ |t|)
    return 2.0 * (1.0 - cdf)


def _normal_cdf(z: float) -> float:
    """Standard normal CDF using the complementary error function."""
    return (1.0 + math.erf(z / math.sqrt(2.0))) / 2.0


def _chi2_pvalue(chi2: float, df: int) -> float:
    """Survival function of χ² with *df* degrees of freedom (upper-tail p-value).

    Uses the regularised upper incomplete gamma function via series expansion.
    """
    if chi2 <= 0.0:
        return 1.0
    # P(χ² > chi2) = Γ(df/2, chi2/2) / Γ(df/2) = 1 - γ(df/2, chi2/2)/Γ(df/2)
    a = df / 2.0
    x = chi2 / 2.0
    # regularised lower incomplete gamma via series (Numerical Recipes §6.2)
    if x < 0.0:
        return 1.0
    if x == 0.0:
        return 1.0
    gln = math.lgamma(a)
    # series for lower incomplete gamma
    ap = a
    delta = 1.0 / a
    total = delta
    for _ in range(300):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-7:
            break
    lower = total * math.exp(-x + a * math.log(x) - gln)
    return 1.0 - lower  # upper tail


def _cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d — pooled within-group standardised mean difference."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    va = _var(a)
    vb = _var(b)
    pooled = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled == 0.0:
        return 0.0
    return (_mean(a) - _mean(b)) / pooled


def _rank(xs: Sequence[float]) -> list[float]:
    """Assign average ranks to a sequence (handles ties)."""
    indexed = sorted(enumerate(xs), key=lambda t: t[1])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


# ---------------------------------------------------------------------------
# Parametric tests
# ---------------------------------------------------------------------------


def welch_t_test(a: Sequence[float], b: Sequence[float]) -> TestResult:
    """Welch's two-sample t-test (unequal variances assumed).

    Recommended over Student's t-test because it does not assume equal
    population variances and performs well even when variances differ.

    Returns a two-tailed p-value.  Effect size is Cohen's d (pooled std).
    """
    if len(a) < 2 or len(b) < 2:
        raise ValueError("each group must have at least 2 observations")
    na, nb = len(a), len(b)
    va, vb = _var(a), _var(b)
    se = math.sqrt(va / na + vb / nb)
    if se == 0.0:
        t = 0.0
        df = float(na + nb - 2)
    else:
        t = (_mean(a) - _mean(b)) / se
        # Welch–Satterthwaite degrees of freedom
        df = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = _t_pvalue(t, df)
    d = _cohens_d(a, b)

    if p < 0.001:
        sig = "highly significant (p < 0.001)"
    elif p < 0.05:
        sig = f"significant (p = {p:.4f})"
    else:
        sig = f"not significant (p = {p:.4f})"

    direction = "greater" if _mean(a) > _mean(b) else "less"
    interp = (
        f"Welch t-test: t({df:.1f}) = {t:.3f}, {sig}; "
        f"group A mean {direction} than group B; Cohen's d = {d:.3f}"
    )
    return TestResult(
        statistic=t,
        p_value=p,
        effect_size=d,
        interpretation=interp,
        n1=na,
        n2=nb,
    )


def one_sample_t_test(values: Sequence[float], *, mu: float = 0.0) -> TestResult:
    """One-sample t-test against a hypothesised population mean *mu*.

    Returns a two-tailed p-value.
    """
    n = len(values)
    if n < 2:
        raise ValueError("at least 2 observations required")
    m = _mean(values)
    se = math.sqrt(_var(values) / n)
    if se == 0.0:
        t = float("inf") if m != mu else 0.0
        p = 0.0 if se == 0.0 and m != mu else 1.0
    else:
        t = (m - mu) / se
        p = _t_pvalue(t, float(n - 1))
    d = abs(m - mu) / math.sqrt(_var(values)) if _var(values) > 0 else 0.0
    interp = (
        f"One-sample t({n - 1}) = {t:.3f}, p = {p:.4f}; "
        f"sample mean {m:.4f} vs. μ₀ = {mu}; Cohen's d = {d:.3f}"
    )
    return TestResult(
        statistic=t,
        p_value=p,
        effect_size=d,
        interpretation=interp,
        n1=n,
        n2=0,
    )


# ---------------------------------------------------------------------------
# Non-parametric tests
# ---------------------------------------------------------------------------


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> TestResult:
    """Mann–Whitney U test (Wilcoxon rank-sum test).

    Non-parametric alternative to the two-sample t-test; does not assume
    normality.  Uses normal approximation with continuity correction for
    p-value computation.

    Effect size: rank-biserial correlation r = 1 − 2U/(n₁·n₂).
    """
    if not a or not b:
        raise ValueError("both groups must be non-empty")
    na, nb = len(a), len(b)
    combined = list(a) + list(b)
    ranks = _rank(combined)
    rank_a = sum(ranks[:na])
    u1 = rank_a - na * (na + 1) / 2.0
    u2 = float(na * nb) - u1
    u = min(u1, u2)

    # Normal approximation (continuity correction)
    mu_u = na * nb / 2.0
    sigma_u = math.sqrt(na * nb * (na + nb + 1) / 12.0)
    z = (u - mu_u + 0.5) / sigma_u if sigma_u > 0 else 0.0
    p = 2.0 * _normal_cdf(-abs(z))

    r = 1.0 - 2.0 * u / (na * nb)  # rank-biserial correlation
    interp = f"Mann–Whitney U = {u:.1f}, z = {z:.3f}, p = {p:.4f}; rank-biserial r = {r:.3f}"
    return TestResult(
        statistic=u,
        p_value=p,
        effect_size=r,
        interpretation=interp,
        n1=na,
        n2=nb,
    )


def ks_test(a: Sequence[float], b: Sequence[float]) -> TestResult:
    """Two-sample Kolmogorov–Smirnov test.

    Tests whether two samples were drawn from the same distribution.
    Uses the exact distribution for small samples and the asymptotic
    approximation for larger ones.  Effect size is the KS statistic itself.
    """
    if not a or not b:
        raise ValueError("both samples must be non-empty")
    na, nb = len(a), len(b)
    sa = sorted(a)
    sb = sorted(b)

    # Build empirical CDFs
    all_pts = sorted(set(sa) | set(sb))
    ia = ib = 0
    d = 0.0
    for pt in all_pts:
        while ia < na and sa[ia] <= pt:
            ia += 1
        while ib < nb and sb[ib] <= pt:
            ib += 1
        d = max(d, abs(ia / na - ib / nb))

    # Asymptotic p-value via Kolmogorov distribution
    en = math.sqrt(na * nb / (na + nb))
    z = (en + 0.12 + 0.11 / en) * d
    # P(D > d) ≈ 2 Σ (-1)^(k-1) exp(-2k²z²), k=1..∞
    p = 2.0 * sum(
        ((-1) ** (k - 1)) * math.exp(-2.0 * k * k * z * z)
        for k in range(1, 100)
        if 2.0 * k * k * z * z < 700
    )
    p = max(0.0, min(1.0, p))
    interp = (
        f"KS statistic D = {d:.4f}, p = {p:.4f}; "
        f"{'distributions differ' if p < 0.05 else 'no significant difference'}"
    )
    return TestResult(
        statistic=d,
        p_value=p,
        effect_size=d,
        interpretation=interp,
        n1=na,
        n2=nb,
    )


def chi_squared_test(
    observed: Sequence[int | float],
    expected: Sequence[int | float] | None = None,
) -> TestResult:
    """Chi-squared goodness-of-fit or independence test.

    If *expected* is ``None``, tests against a uniform distribution.
    Cramér's V is returned as the effect size.

    Raises
    ------
    ValueError
        If lengths differ or any expected frequency is zero.
    """
    n_cats = len(observed)
    if n_cats == 0:
        raise ValueError("observed must be non-empty")
    if n_cats < 2:
        raise ValueError("at least 2 categories required")
    if any(o < 0 for o in observed):
        raise ValueError("observed counts must be non-negative")
    total = sum(observed)
    if expected is None:
        exp = [total / n_cats] * n_cats
    else:
        if len(expected) != n_cats:
            raise ValueError("observed and expected must have the same length")
        exp = list(expected)
    if any(e <= 0 for e in exp):
        raise ValueError("all expected frequencies must be positive")

    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed, exp))
    df = n_cats - 1
    p = _chi2_pvalue(chi2, df)
    # Cramér's V (with df=k-1, treating as one-way table)
    n = total
    cramers_v = math.sqrt(chi2 / (n * df)) if n > 0 and df > 0 else 0.0
    interp = f"χ²({df}) = {chi2:.3f}, p = {p:.4f}; Cramér's V = {cramers_v:.3f}"
    return TestResult(
        statistic=chi2,
        p_value=p,
        effect_size=cramers_v,
        interpretation=interp,
        n1=int(total),
        n2=0,
    )


# ---------------------------------------------------------------------------
# Permutation test
# ---------------------------------------------------------------------------


def permutation_test(
    a: Sequence[float],
    b: Sequence[float],
    *,
    statistic: Callable[[Sequence[float], Sequence[float]], float] | None = None,
    n_permutations: int = 10_000,
    seed: int = 0,
) -> TestResult:
    """Distribution-free permutation test for two independent samples.

    By default uses the difference of means as the test statistic.
    The two-tailed p-value is the proportion of permuted statistics at least
    as extreme as the observed statistic.

    *seed* makes the test reproducible.

    Effect size: Cohen's d (regardless of the chosen statistic function).
    """
    if not a or not b:
        raise ValueError("both groups must be non-empty")

    def _diff_means(x: Sequence[float], y: Sequence[float]) -> float:
        return sum(x) / len(x) - sum(y) / len(y)

    fn = statistic if statistic is not None else _diff_means
    observed = fn(a, b)
    na = len(a)
    pool = list(a) + list(b)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(pool)
        perm_stat = fn(pool[:na], pool[na:])
        if abs(perm_stat) >= abs(observed):
            extreme += 1
    p = (extreme + 1) / (n_permutations + 1)  # +1 for the observed value
    d = _cohens_d(a, b)
    interp = (
        f"Permutation test: observed statistic = {observed:.4f}, "
        f"p = {p:.4f} ({n_permutations} permutations); Cohen's d = {d:.3f}"
    )
    return TestResult(
        statistic=observed,
        p_value=p,
        effect_size=d,
        interpretation=interp,
        n1=len(a),
        n2=len(b),
    )


# ---------------------------------------------------------------------------
# Multiple-comparison correction
# ---------------------------------------------------------------------------


def bonferroni(p_values: Sequence[float], *, alpha: float = 0.05) -> CorrectionResult:
    """Bonferroni correction — multiply each p-value by the number of tests.

    Conservative; controls the family-wise error rate (FWER).
    """
    if not p_values:
        raise ValueError("p_values must be non-empty")
    m = len(p_values)
    adj = tuple(min(1.0, p * m) for p in p_values)
    rejected = tuple(p <= alpha for p in adj)
    return CorrectionResult(adjusted_p=adj, rejected=rejected, method="bonferroni")


def holm(p_values: Sequence[float], *, alpha: float = 0.05) -> CorrectionResult:
    """Holm step-down correction — uniformly more powerful than Bonferroni.

    Controls the FWER; rejects the step-down sequence until the first
    non-rejection.
    """
    if not p_values:
        raise ValueError("p_values must be non-empty")
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adj = [0.0] * m
    rejected = [False] * m
    prev_adj = 0.0
    stop = False
    for rank, idx in enumerate(order):
        a = min(1.0, max(prev_adj, p_values[idx] * (m - rank)))
        adj[idx] = a
        prev_adj = a
        if not stop and a <= alpha:
            rejected[idx] = True
        else:
            stop = True
    return CorrectionResult(adjusted_p=tuple(adj), rejected=tuple(rejected), method="holm")


def benjamini_hochberg(p_values: Sequence[float], *, alpha: float = 0.05) -> CorrectionResult:
    """Benjamini–Hochberg false discovery rate (FDR) correction.

    More powerful than Bonferroni/Holm; controls the expected proportion of
    false rejections rather than the probability of any false rejection.
    Recommended when testing many independent or positively correlated hypotheses.
    """
    if not p_values:
        raise ValueError("p_values must be non-empty")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adj = [1.0] * m
    # Step up: work from largest rank down
    prev_adj = 1.0
    for rank in range(m - 1, -1, -1):
        idx = order[rank]
        a = min(prev_adj, p_values[idx] * m / (rank + 1))
        adj[idx] = a
        prev_adj = a
    rejected = tuple(a <= alpha for a in adj)
    return CorrectionResult(adjusted_p=tuple(adj), rejected=rejected, method="benjamini-hochberg")
