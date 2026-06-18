"""Text similarity and generation quality metrics.

Covers string-edit distance, token-overlap, and NLG evaluation scores
(BLEU, ROUGE-N, ROUGE-L).

All implementations are pure Python; no external dependencies required.

Usage::

    from assay_engine.algorithms.text_metrics import levenshtein, bleu, rouge_n
    d = levenshtein("kitten", "sitting")           # 3
    b = bleu(["the cat sat on the mat"], "the cat sat on the mat")  # 1.0
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BLEUResult:
    """BLEU score decomposition.

    Attributes
    ----------
    score:      Final BLEU score ∈ [0, 1].
    bp:         Brevity penalty.
    precisions: Modified n-gram precision for each n in 1..max_n.
    """

    score: float
    bp: float
    precisions: list[float]


@dataclass(frozen=True)
class ROUGEResult:
    """ROUGE recall/precision/F1 for a single n-gram order or LCS."""

    precision: float
    recall: float
    f1: float


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class StringMetric(Protocol):
    """A callable that computes a distance or similarity between two strings."""

    def __call__(self, a: str, b: str) -> float: ...


# ---------------------------------------------------------------------------
# String-edit distance
# ---------------------------------------------------------------------------


def levenshtein(a: str, b: str) -> int:
    """Levenshtein edit distance (insertions, deletions, substitutions).

    Uses the standard DP formulation; O(|a|·|b|) time and O(min(|a|,|b|)) space.
    Returns 0 when a == b; max(len(a), len(b)) in the worst case.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # Ensure b is the shorter string for space efficiency
    if len(a) < len(b):
        a, b = b, a

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr

    return prev[-1]


def normalized_levenshtein(a: str, b: str) -> float:
    """Levenshtein similarity normalised to [0, 1] (1 = identical).

    Normalisation: 1 − lev(a, b) / max(len(a), len(b)).
    Returns 1.0 for equal strings (including two empty strings).
    """
    if a == b:
        return 1.0
    denom = max(len(a), len(b))
    if denom == 0:
        return 1.0
    return 1.0 - levenshtein(a, b) / denom


def damerau_levenshtein(a: str, b: str) -> int:
    """Damerau–Levenshtein distance (adds transpositions to Levenshtein ops).

    Counts adjacent transpositions (ab → ba) as a single edit.
    Uses the unrestricted (true) Damerau–Levenshtein formulation,
    which satisfies the triangle inequality.
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if not a:
        return lb
    if not b:
        return la

    # Alphabet offset map
    da: dict[str, int] = {}
    for ch in a + b:
        da[ch] = 0

    d = [[0] * (lb + 2) for _ in range(la + 2)]
    maxdist = la + lb
    d[0][0] = maxdist
    for i in range(la + 1):
        d[i + 1][0] = maxdist
        d[i + 1][1] = i
    for j in range(lb + 1):
        d[0][j + 1] = maxdist
        d[1][j + 1] = j

    for i in range(1, la + 1):
        db = 0
        for j in range(1, lb + 1):
            i1 = da.get(b[j - 1], 0)
            j1 = db
            cost = 0 if a[i - 1] == b[j - 1] else 1
            if cost == 0:
                db = j
            d[i + 1][j + 1] = min(
                d[i][j] + cost,
                d[i + 1][j] + 1,
                d[i][j + 1] + 1,
                d[i1][j1] + (i - i1 - 1) + 1 + (j - j1 - 1),
            )
        da[a[i - 1]] = i

    return d[la + 1][lb + 1]


def jaro(a: str, b: str) -> float:
    """Jaro similarity ∈ [0, 1].

    Optimised for short strings (names, identifiers).  Returns 1.0 for
    equal strings, 0.0 for no matching characters.
    """
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0

    match_dist = max(la, lb) // 2 - 1
    a_matches = [False] * la
    b_matches = [False] * lb
    matches = 0
    transpositions = 0

    for i, ca in enumerate(a):
        lo = max(0, i - match_dist)
        hi = min(i + match_dist + 1, lb)
        for j in range(lo, hi):
            if b_matches[j] or ca != b[j]:
                continue
            a_matches[i] = b_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i, ca in enumerate(a):
        if not a_matches[i]:
            continue
        while not b_matches[k]:
            k += 1
        if ca != b[k]:
            transpositions += 1
        k += 1

    return (matches / la + matches / lb + (matches - transpositions / 2) / matches) / 3.0


def jaro_winkler(a: str, b: str, *, p: float = 0.1) -> float:
    """Jaro–Winkler similarity — rewards common prefix agreement.

    *p* is the prefix scaling factor (standard value 0.1; must be ≤ 0.25).
    Preferred for short strings where a common prefix is a strong signal
    (e.g. person names, short identifiers).
    """
    if p > 0.25:
        raise ValueError(f"p must be ≤ 0.25; got {p}")
    j = jaro(a, b)
    prefix = 0
    for ca, cb in zip(a, b):
        if ca != cb or prefix >= 4:
            break
        prefix += 1
    return j + prefix * p * (1.0 - j)


# ---------------------------------------------------------------------------
# Token-overlap similarity
# ---------------------------------------------------------------------------


def jaccard_token(a: str, b: str, *, tokenize: bool = True) -> float:
    """Jaccard index on token sets.

    When *tokenize* is True, both strings are lowercased and split on
    whitespace before comparison.  When False, character-level sets are used.

    Returns 1.0 for identical inputs (including two empty strings).
    """
    if a == b:
        return 1.0
    if tokenize:
        sa: set[str] = set(a.lower().split())
        sb: set[str] = set(b.lower().split())
    else:
        sa = set(a)
        sb = set(b)
    union = sa | sb
    if not union:
        return 1.0
    return len(sa & sb) / len(union)


def ngram_overlap(
    reference: str,
    hypothesis: str,
    *,
    n: int = 2,
    tokenize: bool = True,
) -> float:
    """N-gram overlap — fraction of hypothesis n-grams present in reference.

    Returns 0.0 if the hypothesis has no n-grams; 1.0 for identical inputs.
    """

    def _ngrams(tokens: list[str]) -> Counter[tuple[str, ...]]:
        return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))

    def _tok(s: str) -> list[str]:
        return s.lower().split() if tokenize else list(s)

    ref_toks = _tok(reference)
    hyp_toks = _tok(hypothesis)
    ref_ng = _ngrams(ref_toks)
    hyp_ng = _ngrams(hyp_toks)

    if not hyp_ng:
        return 0.0
    if not ref_ng:
        return 0.0

    clipped = sum(min(hyp_ng[g], ref_ng[g]) for g in hyp_ng)
    return clipped / sum(hyp_ng.values())


# ---------------------------------------------------------------------------
# BLEU
# ---------------------------------------------------------------------------


def bleu(
    references: Sequence[str],
    hypothesis: str,
    *,
    max_n: int = 4,
    weights: Sequence[float] | None = None,
) -> BLEUResult:
    """Sentence-level BLEU with brevity penalty.

    *references* is a list of reference translations; *hypothesis* is the
    candidate.  Implements the standard Papineni et al. (2002) formulation.

    Parameters
    ----------
    references: One or more reference strings (whitespace-tokenised).
    hypothesis: The candidate string.
    max_n:      Maximum n-gram order (default 4).
    weights:    Per-order weights (default uniform: 1/max_n each).
    """
    if not references:
        raise ValueError("at least one reference is required")
    if weights is None:
        weights = [1.0 / max_n] * max_n
    if len(weights) != max_n:
        raise ValueError(f"weights must have length {max_n}; got {len(weights)}")

    def _tok(s: str) -> list[str]:
        return s.lower().split()

    def _ngrams(tokens: list[str], n: int) -> Counter[tuple[str, ...]]:
        return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))

    hyp_tok = _tok(hypothesis)
    ref_toks = [_tok(r) for r in references]

    hyp_len = len(hyp_tok)
    closest_ref_len = min((abs(len(r) - hyp_len), len(r)) for r in ref_toks)[1]

    precisions: list[float] = []
    for n in range(1, max_n + 1):
        hyp_ng = _ngrams(hyp_tok, n)
        if not hyp_ng:
            precisions.append(0.0)
            continue

        max_ref_count: Counter[tuple[str, ...]] = Counter()
        for ref in ref_toks:
            ref_ng = _ngrams(ref, n)
            for gram, cnt in ref_ng.items():
                max_ref_count[gram] = max(max_ref_count[gram], cnt)

        clipped = sum(min(cnt, max_ref_count[gram]) for gram, cnt in hyp_ng.items())
        total = sum(hyp_ng.values())
        precisions.append(clipped / total if total > 0 else 0.0)

    if any(p == 0.0 for p in precisions):
        return BLEUResult(score=0.0, bp=0.0, precisions=precisions)

    log_bleu = sum(w * math.log(p) for w, p in zip(weights, precisions))
    bp = 1.0 if hyp_len > closest_ref_len else math.exp(1 - closest_ref_len / hyp_len)
    score = bp * math.exp(log_bleu)

    return BLEUResult(score=score, bp=bp, precisions=precisions)


# ---------------------------------------------------------------------------
# ROUGE
# ---------------------------------------------------------------------------


def rouge_n(
    reference: str,
    hypothesis: str,
    *,
    n: int = 2,
    tokenize: bool = True,
) -> ROUGEResult:
    """ROUGE-N — n-gram overlap recall/precision/F1.

    Computes the standard Lin (2004) ROUGE-N metric.

    Parameters
    ----------
    n: N-gram order (default 2 for ROUGE-2).
    """

    def _tok(s: str) -> list[str]:
        return s.lower().split() if tokenize else list(s)

    def _ngrams(tokens: list[str]) -> Counter[tuple[str, ...]]:
        return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))

    ref_ng = _ngrams(_tok(reference))
    hyp_ng = _ngrams(_tok(hypothesis))

    if not ref_ng:
        return ROUGEResult(precision=0.0, recall=0.0, f1=0.0)
    if not hyp_ng:
        return ROUGEResult(precision=0.0, recall=0.0, f1=0.0)

    match = sum(min(hyp_ng[g], ref_ng[g]) for g in hyp_ng)
    ref_total = sum(ref_ng.values())
    hyp_total = sum(hyp_ng.values())

    recall = match / ref_total if ref_total > 0 else 0.0
    precision = match / hyp_total if hyp_total > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return ROUGEResult(precision=precision, recall=recall, f1=f1)


def rouge_l(
    reference: str,
    hypothesis: str,
    *,
    tokenize: bool = True,
    beta: float = 1.2,
) -> ROUGEResult:
    """ROUGE-L — Longest Common Subsequence based F-measure.

    Uses the Lin (2004) sentence-level LCS formulation with the default
    β = 1.2 (slightly recall-biased, per the original paper).

    Parameters
    ----------
    beta: Balances precision and recall (β > 1 weights recall higher).
    """

    def _tok(s: str) -> list[str]:
        return s.lower().split() if tokenize else list(s)

    ref_toks = _tok(reference)
    hyp_toks = _tok(hypothesis)
    lr = len(ref_toks)
    lh = len(hyp_toks)

    if lr == 0 or lh == 0:
        return ROUGEResult(precision=0.0, recall=0.0, f1=0.0)

    # LCS via DP
    dp = [[0] * (lh + 1) for _ in range(lr + 1)]
    for i in range(1, lr + 1):
        for j in range(1, lh + 1):
            if ref_toks[i - 1] == hyp_toks[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs = dp[lr][lh]
    recall = lcs / lr
    precision = lcs / lh

    b2 = beta**2
    denom = b2 * precision + recall
    f1 = (1 + b2) * precision * recall / denom if denom > 0 else 0.0

    return ROUGEResult(precision=precision, recall=recall, f1=f1)


def rouge_s(
    reference: str,
    hypothesis: str,
    *,
    tokenize: bool = True,
    beta: float = 1.2,
    skip_distance: int | None = None,
) -> ROUGEResult:
    """ROUGE-S — skip-bigram co-occurrence statistics.

    Skip-bigrams are any pair of words taken in order, allowing gaps
    (bounded by *skip_distance* if given, or unbounded).

    Parameters
    ----------
    skip_distance: Maximum gap between words (None = unbounded ROUGE-S).
    beta:          F-score balance parameter.
    """

    def _tok(s: str) -> list[str]:
        return s.lower().split() if tokenize else list(s)

    def _skip_bigrams(tokens: list[str]) -> Counter[tuple[str, str]]:
        pairs: Counter[tuple[str, str]] = Counter()
        n = len(tokens)
        for i in range(n):
            limit = n if skip_distance is None else min(n, i + skip_distance + 2)
            for j in range(i + 1, limit):
                pairs[(tokens[i], tokens[j])] += 1
        return pairs

    ref_toks = _tok(reference)
    hyp_toks = _tok(hypothesis)

    ref_skip = _skip_bigrams(ref_toks)
    hyp_skip = _skip_bigrams(hyp_toks)

    if not ref_skip or not hyp_skip:
        return ROUGEResult(precision=0.0, recall=0.0, f1=0.0)

    match = sum(min(hyp_skip[g], ref_skip[g]) for g in hyp_skip)
    recall = match / sum(ref_skip.values())
    precision = match / sum(hyp_skip.values())

    b2 = beta**2
    denom = b2 * precision + recall
    f1 = (1 + b2) * precision * recall / denom if denom > 0 else 0.0

    return ROUGEResult(precision=precision, recall=recall, f1=f1)
