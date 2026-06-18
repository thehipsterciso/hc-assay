"""Tests for assay_engine.algorithms.text_metrics."""

import pytest

from assay_engine.algorithms.text_metrics import (
    BLEUResult,
    ROUGEResult,
    bleu,
    damerau_levenshtein,
    jaccard_token,
    jaro,
    jaro_winkler,
    levenshtein,
    ngram_overlap,
    normalized_levenshtein,
    rouge_l,
    rouge_n,
    rouge_s,
)


# ---------------------------------------------------------------------------
# levenshtein
# ---------------------------------------------------------------------------


class TestLevenshtein:
    def test_identical(self) -> None:
        assert levenshtein("kitten", "kitten") == 0

    def test_classic(self) -> None:
        assert levenshtein("kitten", "sitting") == 3

    def test_empty_vs_nonempty(self) -> None:
        assert levenshtein("", "abc") == 3
        assert levenshtein("abc", "") == 3

    def test_both_empty(self) -> None:
        assert levenshtein("", "") == 0

    def test_one_char_diff(self) -> None:
        assert levenshtein("cat", "bat") == 1

    def test_insertion(self) -> None:
        assert levenshtein("abc", "abcd") == 1

    def test_deletion(self) -> None:
        assert levenshtein("abcd", "abc") == 1

    def test_symmetry(self) -> None:
        assert levenshtein("foo", "bar") == levenshtein("bar", "foo")


# ---------------------------------------------------------------------------
# normalized_levenshtein
# ---------------------------------------------------------------------------


class TestNormalizedLevenshtein:
    def test_identical(self) -> None:
        assert normalized_levenshtein("hello", "hello") == pytest.approx(1.0)

    def test_completely_different(self) -> None:
        score = normalized_levenshtein("abc", "xyz")
        assert 0.0 <= score <= 1.0

    def test_both_empty(self) -> None:
        assert normalized_levenshtein("", "") == pytest.approx(1.0)

    def test_range(self) -> None:
        score = normalized_levenshtein("kitten", "sitting")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# damerau_levenshtein
# ---------------------------------------------------------------------------


class TestDamerauLevenshtein:
    def test_identical(self) -> None:
        assert damerau_levenshtein("abc", "abc") == 0

    def test_transposition(self) -> None:
        # 'ab' → 'ba' is one transposition
        assert damerau_levenshtein("ab", "ba") == 1

    def test_classic_levenshtein(self) -> None:
        # When no transpositions occur, should match Levenshtein
        assert damerau_levenshtein("kitten", "sitting") == levenshtein("kitten", "sitting")

    def test_empty(self) -> None:
        assert damerau_levenshtein("", "abc") == 3


# ---------------------------------------------------------------------------
# jaro
# ---------------------------------------------------------------------------


class TestJaro:
    def test_identical(self) -> None:
        assert jaro("martha", "martha") == pytest.approx(1.0)

    def test_different(self) -> None:
        assert jaro("martha", "marhta") > 0.9

    def test_completely_different(self) -> None:
        assert jaro("abc", "xyz") < 0.5

    def test_empty_strings(self) -> None:
        assert jaro("", "") == pytest.approx(1.0)
        assert jaro("a", "") == pytest.approx(0.0)

    def test_range(self) -> None:
        score = jaro("foo", "bar")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# jaro_winkler
# ---------------------------------------------------------------------------


class TestJaroWinkler:
    def test_identical(self) -> None:
        assert jaro_winkler("MARTHA", "MARTHA") == pytest.approx(1.0)

    def test_common_prefix_boost(self) -> None:
        # Jaro-Winkler should be ≥ Jaro when there's a common prefix
        a, b = "MARTHA", "MARHTA"
        assert jaro_winkler(a, b) >= jaro(a, b)

    def test_p_too_large_raises(self) -> None:
        with pytest.raises(ValueError):
            jaro_winkler("a", "b", p=0.3)


# ---------------------------------------------------------------------------
# jaccard_token
# ---------------------------------------------------------------------------


class TestJaccardToken:
    def test_identical(self) -> None:
        assert jaccard_token("hello world", "hello world") == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        assert jaccard_token("cat sat", "dog run") == pytest.approx(0.0)

    def test_partial_overlap(self) -> None:
        score = jaccard_token("cat sat", "cat ran")
        assert 0.0 < score < 1.0

    def test_case_insensitive(self) -> None:
        assert jaccard_token("Hello World", "hello world") == pytest.approx(1.0)

    def test_char_mode(self) -> None:
        score = jaccard_token("abc", "abc", tokenize=False)
        assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ngram_overlap
# ---------------------------------------------------------------------------


class TestNgramOverlap:
    def test_identical(self) -> None:
        assert ngram_overlap("the cat sat", "the cat sat", n=2) == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        assert ngram_overlap("cat dog", "fish bird", n=1) == pytest.approx(0.0)

    def test_partial_overlap(self) -> None:
        score = ngram_overlap("the cat sat on the mat", "the cat ran", n=2)
        assert 0.0 < score < 1.0

    def test_unigram(self) -> None:
        score = ngram_overlap("a b c", "a b", n=1)
        assert score == pytest.approx(1.0)  # all hyp unigrams in ref


# ---------------------------------------------------------------------------
# BLEU
# ---------------------------------------------------------------------------


class TestBLEU:
    REF = "the cat sat on the mat"
    HYP = "the cat sat on the mat"

    def test_perfect_score(self) -> None:
        result = bleu([self.REF], self.HYP)
        assert result.score == pytest.approx(1.0)

    def test_wrong_hypothesis(self) -> None:
        result = bleu([self.REF], "dogs and cats")
        assert result.score < 1.0

    def test_result_type(self) -> None:
        result = bleu([self.REF], self.HYP)
        assert isinstance(result, BLEUResult)

    def test_precisions_length(self) -> None:
        result = bleu([self.REF], self.HYP, max_n=4)
        assert len(result.precisions) == 4

    def test_empty_references_raise(self) -> None:
        with pytest.raises(ValueError):
            bleu([], self.HYP)

    def test_zero_score_for_no_overlap(self) -> None:
        result = bleu(["the quick brown fox"], "xyz zzz qqq aaa")
        assert result.score == pytest.approx(0.0)

    def test_bp_brevity_penalty(self) -> None:
        # Short hypothesis → BP < 1
        result = bleu(["a long reference sentence"], "short")
        assert result.bp < 1.0


# ---------------------------------------------------------------------------
# ROUGE-N
# ---------------------------------------------------------------------------


class TestROUGEN:
    def test_perfect(self) -> None:
        result = rouge_n("the cat sat", "the cat sat", n=2)
        assert result.f1 == pytest.approx(1.0)
        assert result.precision == pytest.approx(1.0)
        assert result.recall == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        result = rouge_n("cat dog", "fish bird", n=1)
        assert result.f1 == pytest.approx(0.0)

    def test_result_type(self) -> None:
        result = rouge_n("abc", "abc")
        assert isinstance(result, ROUGEResult)

    def test_range(self) -> None:
        result = rouge_n("the cat sat on the mat", "cat sat mat", n=1)
        assert 0.0 <= result.precision <= 1.0
        assert 0.0 <= result.recall <= 1.0
        assert 0.0 <= result.f1 <= 1.0

    def test_empty_ref_zero(self) -> None:
        result = rouge_n("", "something", n=1)
        assert result.f1 == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# ROUGE-L
# ---------------------------------------------------------------------------


class TestROUGEL:
    def test_perfect(self) -> None:
        result = rouge_l("the cat sat", "the cat sat")
        assert result.recall == pytest.approx(1.0)
        assert result.precision == pytest.approx(1.0)

    def test_partial_overlap(self) -> None:
        result = rouge_l("the cat sat on the mat", "the cat ran")
        assert 0.0 < result.f1 < 1.0

    def test_no_overlap(self) -> None:
        result = rouge_l("abc", "xyz")
        assert result.f1 == pytest.approx(0.0)

    def test_empty_inputs(self) -> None:
        result = rouge_l("", "something")
        assert result.f1 == pytest.approx(0.0)

    def test_result_type(self) -> None:
        result = rouge_l("abc", "abc")
        assert isinstance(result, ROUGEResult)


# ---------------------------------------------------------------------------
# ROUGE-S
# ---------------------------------------------------------------------------


class TestROUGES:
    def test_identical(self) -> None:
        result = rouge_s("cat dog fox", "cat dog fox")
        assert result.f1 == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        result = rouge_s("cat dog", "fish bird")
        assert result.f1 == pytest.approx(0.0)

    def test_skip_distance_limits(self) -> None:
        # With skip_distance=0, only adjacent pairs count
        unlimited = rouge_s("a b c d", "a d", skip_distance=None)
        limited = rouge_s("a b c d", "a d", skip_distance=1)
        # Unlimited allows (a,d) which is a gap of 2; limited (gap=1) does not
        assert unlimited.recall >= limited.recall
