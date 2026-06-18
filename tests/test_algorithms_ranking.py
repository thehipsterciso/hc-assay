"""Tests for assay_engine.algorithms.ranking."""

import pytest

from assay_engine.algorithms.ranking import (
    RankingResult,
    average_precision,
    bm25_score,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    reciprocal_rank_fusion,
    tfidf_score,
)


# ---------------------------------------------------------------------------
# TF-IDF
# ---------------------------------------------------------------------------


class TestTFIDF:
    CORPUS = ["the cat sat on the mat", "the dog sat on the log", "cats and dogs"]

    def test_relevant_ranked_first(self) -> None:
        result = tfidf_score(self.CORPUS, "cat")
        assert result.ranked_indices[0] == 0

    def test_empty_query_all_zero(self) -> None:
        result = tfidf_score(self.CORPUS, "")
        for sd in result.scores:
            assert sd.score == pytest.approx(0.0)

    def test_result_sorted_descending(self) -> None:
        result = tfidf_score(self.CORPUS, "cat dog")
        scores = [sd.score for sd in result.scores]
        assert scores == sorted(scores, reverse=True)

    def test_single_doc(self) -> None:
        # query "hello" vs doc "hello world": cosine = 1/√2 ≈ 0.707
        result = tfidf_score(["hello world"], "hello")
        assert result.scores[0].score == pytest.approx(1.0 / 2**0.5, abs=1e-6)

    def test_pretokenised_input(self) -> None:
        result = tfidf_score([["the", "cat"], ["the", "dog"]], ["cat"])
        assert result.ranked_indices[0] == 0

    def test_result_type(self) -> None:
        result = tfidf_score(self.CORPUS, "cat")
        assert isinstance(result, RankingResult)

    def test_all_indices_present(self) -> None:
        result = tfidf_score(self.CORPUS, "cat")
        assert sorted(result.ranked_indices) == list(range(len(self.CORPUS)))


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


class TestBM25:
    CORPUS = ["the cat sat on the mat", "the dog sat on the log", "cats and dogs"]

    def test_relevant_ranked_first(self) -> None:
        result = bm25_score(self.CORPUS, "cat")
        assert result.ranked_indices[0] == 0

    def test_scores_nonnegative(self) -> None:
        result = bm25_score(self.CORPUS, "cat dog")
        for sd in result.scores:
            assert sd.score >= 0.0

    def test_unknown_term_zero_score(self) -> None:
        result = bm25_score(self.CORPUS, "zzzzquux")
        for sd in result.scores:
            assert sd.score == pytest.approx(0.0)

    def test_sorted_descending(self) -> None:
        result = bm25_score(self.CORPUS, "dog cats")
        scores = [sd.score for sd in result.scores]
        assert scores == sorted(scores, reverse=True)

    def test_empty_corpus_returns_empty(self) -> None:
        result = bm25_score([], "cat")
        assert result.scores == []

    def test_pretokenised_input(self) -> None:
        result = bm25_score([["cat", "sat"], ["dog", "sat"]], ["cat"])
        assert result.ranked_indices[0] == 0


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


class TestRRF:
    def test_consistent_top_doc(self) -> None:
        ranked = reciprocal_rank_fusion([[0, 1, 2], [0, 2, 1]])
        top_doc = ranked[0][0]
        assert top_doc == 0

    def test_all_docs_present(self) -> None:
        ranked = reciprocal_rank_fusion([[0, 1, 2], [2, 1, 0]])
        assert sorted(d for d, _ in ranked) == [0, 1, 2]

    def test_scores_positive(self) -> None:
        ranked = reciprocal_rank_fusion([[0, 1]])
        for _, score in ranked:
            assert score > 0.0

    def test_single_list(self) -> None:
        ranked = reciprocal_rank_fusion([[3, 1, 2]])
        assert ranked[0][0] == 3


# ---------------------------------------------------------------------------
# nDCG
# ---------------------------------------------------------------------------


class TestNDCG:
    def test_perfect_ranking(self) -> None:
        assert ndcg([3, 2, 1, 0]) == pytest.approx(1.0)

    def test_worst_ranking(self) -> None:
        score = ndcg([0, 1, 2, 3])
        assert score < 1.0

    def test_at_k_truncates(self) -> None:
        # First element is highly relevant; truncating at k=1 gives perfect score
        assert ndcg([3, 0, 0, 0], k=1) == pytest.approx(1.0)

    def test_all_zero_relevance(self) -> None:
        assert ndcg([0, 0, 0]) == pytest.approx(0.0)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            ndcg([])


# ---------------------------------------------------------------------------
# Average Precision
# ---------------------------------------------------------------------------


class TestAveragePrecision:
    def test_perfect(self) -> None:
        assert average_precision({0, 1}, [0, 1, 2]) == pytest.approx(1.0)

    def test_no_relevant(self) -> None:
        assert average_precision(set(), [0, 1, 2]) == pytest.approx(0.0)

    def test_relevant_at_end(self) -> None:
        ap = average_precision({2}, [0, 1, 2])
        assert ap < 1.0
        assert ap > 0.0


# ---------------------------------------------------------------------------
# MAP
# ---------------------------------------------------------------------------


class TestMAP:
    def test_perfect(self) -> None:
        assert mean_average_precision([{0}, {1}], [[0, 1], [1, 0]]) == pytest.approx(1.0)

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError):
            mean_average_precision([{0}], [[0], [1]])

    def test_empty_returns_zero(self) -> None:
        assert mean_average_precision([], []) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Reciprocal Rank / MRR
# ---------------------------------------------------------------------------


class TestRR:
    def test_first_position(self) -> None:
        assert reciprocal_rank({0}, [0, 1, 2]) == pytest.approx(1.0)

    def test_second_position(self) -> None:
        assert reciprocal_rank({1}, [0, 1, 2]) == pytest.approx(0.5)

    def test_not_found(self) -> None:
        assert reciprocal_rank({5}, [0, 1, 2]) == pytest.approx(0.0)

    def test_mrr(self) -> None:
        mrr = mean_reciprocal_rank([{0}, {1}], [[0, 1], [0, 1]])
        assert mrr == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Precision/Recall at k
# ---------------------------------------------------------------------------


class TestPrecisionRecallAtK:
    def test_precision_at_k(self) -> None:
        assert precision_at_k({0, 1}, [0, 2, 1], k=2) == pytest.approx(0.5)

    def test_recall_at_k(self) -> None:
        assert recall_at_k({0, 1}, [0, 2, 1], k=3) == pytest.approx(1.0)

    def test_k_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            precision_at_k({0}, [0], k=0)
