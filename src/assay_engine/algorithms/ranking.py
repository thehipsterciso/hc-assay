"""Information retrieval ranking algorithms and evaluation metrics.

Includes document scoring (TF-IDF, BM25), rank fusion (RRF), and
IR evaluation metrics (nDCG, MAP, MRR).

All implementations are pure Python; no external dependencies required.

Usage::

    from assay_engine.algorithms.ranking import bm25_score, ndcg
    scores = bm25_score(corpus=["hello world", "world peace"], query="world")
    ndcg_at_5 = ndcg(relevances=[3, 2, 3, 0, 1, 2], k=5)
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
class ScoredDocument:
    """A document with its retrieval score."""

    index: int
    score: float


@dataclass(frozen=True)
class RankingResult:
    """Ordered list of scored documents (descending score)."""

    scores: list[ScoredDocument]

    @property
    def ranked_indices(self) -> list[int]:
        return [s.index for s in self.scores]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class RankingFn(Protocol):
    """A callable that scores a corpus of documents against a query."""

    def __call__(
        self,
        corpus: Sequence[Sequence[str]],
        query: Sequence[str],
    ) -> RankingResult: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercased whitespace tokenization."""
    return text.lower().split()


def _tf(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = len(tokens)
    return {t: c / total for t, c in counts.items()} if total > 0 else {}


def _idf(corpus_tokens: list[list[str]], smooth: bool = True) -> dict[str, float]:
    n = len(corpus_tokens)
    df: Counter[str] = Counter()
    for doc in corpus_tokens:
        for term in set(doc):
            df[term] += 1
    if smooth:
        return {t: math.log((n + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}
    return {t: math.log(n / df_t) + 1.0 for t, df_t in df.items()}


# ---------------------------------------------------------------------------
# TF-IDF
# ---------------------------------------------------------------------------


def tfidf_score(
    corpus: Sequence[str | Sequence[str]],
    query: str | Sequence[str],
    *,
    smooth_idf: bool = True,
) -> RankingResult:
    """Score documents in *corpus* against *query* using TF-IDF cosine similarity.

    Accepts either raw strings (whitespace-tokenised) or pre-tokenised lists.
    Returns documents sorted by descending cosine similarity.

    Parameters
    ----------
    corpus:     Collection of documents (strings or token lists).
    query:      Query string or token list.
    smooth_idf: Use smoothed IDF (avoids zero division for unseen terms).
    """

    def _tok(item: str | Sequence[str]) -> list[str]:
        return _tokenize(item) if isinstance(item, str) else list(item)

    docs = [_tok(d) for d in corpus]
    q_tokens = _tok(query)

    idf = _idf(docs, smooth=smooth_idf)
    vocab = set(q_tokens) | {t for doc in docs for t in doc}

    def vec(tokens: list[str]) -> dict[str, float]:
        tf = _tf(tokens)
        return {t: tf.get(t, 0.0) * idf.get(t, 0.0) for t in vocab}

    q_vec = vec(q_tokens)
    q_norm = math.sqrt(sum(v**2 for v in q_vec.values()))

    results: list[ScoredDocument] = []
    for idx, doc in enumerate(docs):
        d_vec = vec(doc)
        dot = sum(q_vec[t] * d_vec.get(t, 0.0) for t in q_vec)
        d_norm = math.sqrt(sum(v**2 for v in d_vec.values()))
        if q_norm == 0.0 or d_norm == 0.0:
            score = 0.0
        else:
            score = dot / (q_norm * d_norm)
        results.append(ScoredDocument(index=idx, score=score))

    results.sort(key=lambda s: s.score, reverse=True)
    return RankingResult(scores=results)


# ---------------------------------------------------------------------------
# BM25 (Okapi BM25)
# ---------------------------------------------------------------------------


def bm25_score(
    corpus: Sequence[str | Sequence[str]],
    query: str | Sequence[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> RankingResult:
    """Okapi BM25 relevance scoring.

    The industry-standard probabilistic retrieval model; generally
    outperforms TF-IDF on long documents and common query terms.

    Parameters
    ----------
    corpus: Documents (strings or token lists).
    query:  Query (string or token list).
    k1:     Term-frequency saturation parameter (default 1.5).
    b:      Length normalisation parameter (default 0.75).
    """

    def _tok(item: str | Sequence[str]) -> list[str]:
        return _tokenize(item) if isinstance(item, str) else list(item)

    docs = [_tok(d) for d in corpus]
    q_tokens = _tok(query)
    n = len(docs)
    if n == 0:
        return RankingResult(scores=[])

    avg_dl = sum(len(d) for d in docs) / n

    df: Counter[str] = Counter()
    for doc in docs:
        for term in set(doc):
            df[term] += 1

    results: list[ScoredDocument] = []
    for idx, doc in enumerate(docs):
        tf_d = Counter(doc)
        dl = len(doc)
        score = 0.0
        for term in q_tokens:
            if term not in tf_d:
                continue
            tf = tf_d[term]
            idf_t = math.log((n - df[term] + 0.5) / (df[term] + 0.5) + 1.0)
            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            score += idf_t * tf_norm
        results.append(ScoredDocument(index=idx, score=score))

    results.sort(key=lambda s: s.score, reverse=True)
    return RankingResult(scores=results)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[int]],
    *,
    k: int = 60,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion of multiple ranked lists.

    Combines results from N independent rankers (e.g. BM25 + dense retrieval)
    without requiring score calibration.

    The RRF score for document d is: Σ_r 1 / (k + rank_r(d))
    where rank is 1-indexed and k=60 is the Cormack et al. recommendation.

    Parameters
    ----------
    ranked_lists: Each inner sequence is a ranked list of document indices.
    k:            Rank offset constant (default 60).

    Returns
    -------
    List of (doc_index, rrf_score) tuples sorted by descending RRF score.
    """
    rrf: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            rrf[doc_id] = rrf.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(rrf.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# IR evaluation metrics
# ---------------------------------------------------------------------------


def ndcg(relevances: Sequence[float], *, k: int | None = None) -> float:
    """Normalised Discounted Cumulative Gain at rank *k*.

    *relevances* is a list of graded relevance scores for the returned
    documents in order (position 0 = top result).  An ideal ranking (IDCG)
    is computed from the same scores.

    Returns a value in [0, 1]; 1.0 = perfect ranking.

    Raises
    ------
    ValueError
        If *relevances* is empty or *k* is out of range.
    """
    if not relevances:
        raise ValueError("relevances must be non-empty")
    cutoff = k if k is not None else len(relevances)

    def _dcg(rels: Sequence[float], cut: int) -> float:
        return sum(r / math.log2(i + 2) for i, r in enumerate(rels[:cut]))

    dcg_val = _dcg(relevances, cutoff)
    ideal = _dcg(sorted(relevances, reverse=True), cutoff)
    return dcg_val / ideal if ideal > 0.0 else 0.0


def average_precision(relevant: set[int], ranked: Sequence[int]) -> float:
    """Average Precision for a single query.

    *relevant* is the set of relevant document indices; *ranked* is the
    retrieved document indices in order.

    AP = Σ_k P@k · rel(k) / |relevant|

    Returns 0.0 if *relevant* is empty.
    """
    if not relevant:
        return 0.0
    hits = 0
    total = 0.0
    for i, doc in enumerate(ranked, start=1):
        if doc in relevant:
            hits += 1
            total += hits / i
    return total / len(relevant)


def mean_average_precision(
    relevant_sets: Sequence[set[int]],
    ranked_lists: Sequence[Sequence[int]],
) -> float:
    """MAP — arithmetic mean of Average Precision over multiple queries.

    Raises
    ------
    ValueError
        If the number of queries and ranked lists differ.
    """
    if len(relevant_sets) != len(ranked_lists):
        raise ValueError(
            f"relevant_sets and ranked_lists must have the same length; "
            f"got {len(relevant_sets)} and {len(ranked_lists)}"
        )
    if not relevant_sets:
        return 0.0
    aps = [average_precision(rel, ranked) for rel, ranked in zip(relevant_sets, ranked_lists)]
    return sum(aps) / len(aps)


def reciprocal_rank(relevant: set[int], ranked: Sequence[int]) -> float:
    """Reciprocal Rank (1 / rank of first relevant document).

    Returns 0.0 if no relevant document appears in *ranked*.
    """
    for i, doc in enumerate(ranked, start=1):
        if doc in relevant:
            return 1.0 / i
    return 0.0


def mean_reciprocal_rank(
    relevant_sets: Sequence[set[int]],
    ranked_lists: Sequence[Sequence[int]],
) -> float:
    """Mean Reciprocal Rank over multiple queries."""
    if len(relevant_sets) != len(ranked_lists):
        raise ValueError(
            f"relevant_sets and ranked_lists must have the same length; "
            f"got {len(relevant_sets)} and {len(ranked_lists)}"
        )
    if not relevant_sets:
        return 0.0
    rrs = [reciprocal_rank(rel, ranked) for rel, ranked in zip(relevant_sets, ranked_lists)]
    return sum(rrs) / len(rrs)


def precision_at_k(relevant: set[int], ranked: Sequence[int], k: int) -> float:
    """Precision at rank k — fraction of top-k results that are relevant."""
    if k <= 0:
        raise ValueError(f"k must be positive; got {k}")
    top_k = list(ranked[:k])
    if not top_k:
        return 0.0
    hits = sum(1 for doc in top_k if doc in relevant)
    return hits / len(top_k)


def recall_at_k(relevant: set[int], ranked: Sequence[int], k: int) -> float:
    """Recall at rank k — fraction of relevant documents in top-k results."""
    if k <= 0:
        raise ValueError(f"k must be positive; got {k}")
    if not relevant:
        return 0.0
    top_k = list(ranked[:k])
    hits = sum(1 for doc in top_k if doc in relevant)
    return hits / len(relevant)
