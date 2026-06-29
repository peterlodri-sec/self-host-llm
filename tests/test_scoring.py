# SPDX-License-Identifier: MIT
"""Tests for quality scoring functions."""

import pytest
from ultrawhale.scoring import (
    calculate_quality_score,
    token_count,
    reset_seen_hashes,
    QUALITY_THRESHOLDS,
)


class TestTokenCount:
    def test_empty_string(self):
        assert token_count("") == 0

    def test_single_word(self):
        assert token_count("hello") == 1

    def test_multiple_words(self):
        assert token_count("hello world this is a test") == 6

    def test_whitespace_only(self):
        assert token_count("   ") == 0


class TestQualityScoring:
    def setup_method(self):
        reset_seen_hashes()

    def test_perfect_pair_scores_high(self):
        question = "What is the time complexity of binary search and how does it compare to linear search?"
        answer = "Binary search has O(log n) time complexity, while linear search is O(n). Binary search requires a sorted array and repeatedly divides the search interval in half."
        score, breakdown = calculate_quality_score(question, answer, "algorithms")
        assert score > 0.7, f"Expected high score, got {score}: {breakdown}"

    def test_empty_question_scores_low(self):
        score, breakdown = calculate_quality_score("", "some answer", "algorithms")
        # Empty question gets low length + coherence scores, but punctuation and diversity help
        assert score < 0.7, f"Expected low score for empty question, got {score}"
        assert breakdown["length"] < 0.7

    def test_empty_answer_scores_low(self):
        score, breakdown = calculate_quality_score("some question?", "", "algorithms")
        assert score < 0.7, f"Expected low score for empty answer, got {score}"
        assert breakdown["length"] < 0.7

    def test_duplicate_detection(self):
        q = "What is a binary tree?"
        a = "A tree where each node has at most two children."
        score1, _ = calculate_quality_score(q, a, "algorithms")
        score2, _ = calculate_quality_score(q, a, "algorithms")
        # Second should have low diversity score
        assert score2 < score1, f"Duplicate should score lower. First: {score1}, second: {score2}"

    def test_very_long_answer_penalized(self):
        q = "What is Python?"
        a = "x" * 5000  # way over max_answer_tokens
        score, breakdown = calculate_quality_score(q, a, "general")
        assert breakdown["length"] < 0.6, f"Long answer should get low length score: {breakdown}"

    def test_score_bounded_0_to_1(self):
        q = "What is X?"
        a = "It means Y and Z combined with careful consideration of all factors."
        score, _ = calculate_quality_score(q, a, "general")
        assert 0.0 <= score <= 1.0, f"Score {score} out of bounds"

    def test_no_punctuation_lowers_coherence(self):
        q_with = "What is a hash table?"
        a_with = "A data structure that maps keys to values using a hash function."
        score_with, bd_with = calculate_quality_score(q_with, a_with, "algorithms")

        reset_seen_hashes()
        score_without, bd_without = calculate_quality_score(
            "what is a hash table",
            "a data structure that maps keys to values using a hash function",
            "algorithms"
        )
        assert bd_without["coherence"] < bd_with["coherence"], \
            f"No punctuation should reduce coherence: with={bd_with['coherence']}, without={bd_without['coherence']}"

    def test_answer_shorter_than_question_penalized(self):
        q = "Explain the difference between TCP and UDP in detail including their use cases and tradeoffs."
        a = "TCP is reliable, UDP is fast."
        score, breakdown = calculate_quality_score(q, a, "networking")
        assert breakdown["coherence"] < 0.8, f"Short answer should reduce coherence: {breakdown}"

    def test_reset_clears_duplicates(self):
        q, a = "test Q?", "test A."
        calculate_quality_score(q, a, "test")
        reset_seen_hashes()
        score_after_reset, _ = calculate_quality_score(q, a, "test")
        # Should be high again since hash set was cleared
        assert score_after_reset > 0.6
