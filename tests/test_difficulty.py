# SPDX-License-Identifier: MIT
"""Tests for difficulty sampling and active learning."""

import pytest
from ultrawhale.difficulty import (
    select_difficulty,
    get_question_type_for_difficulty,
    get_prompt_for_difficulty,
    ActiveLearningTracker,
    DIFFICULTY_DISTRIBUTION,
)


class TestDifficultySelection:
    def test_select_difficulty_returns_valid(self):
        result = select_difficulty()
        assert result in ("easy", "medium", "hard")

    def test_distribution_approximate(self):
        """Over 1000 samples, distribution should approximate 40/40/20."""
        samples = [select_difficulty(seed=i) for i in range(1000)]
        easy = samples.count("easy")
        medium = samples.count("medium")
        hard = samples.count("hard")
        # Allow ±5% tolerance
        assert 350 <= easy <= 450, f"Easy: {easy}/1000"
        assert 350 <= medium <= 450, f"Medium: {medium}/1000"
        assert 150 <= hard <= 250, f"Hard: {hard}/1000"

    def test_seeded_reproducibility(self):
        """Same seed should produce same result."""
        a = select_difficulty(seed=42)
        b = select_difficulty(seed=42)
        assert a == b

    def test_no_global_seed_side_effect(self):
        """Calling select_difficulty with seed should not affect subsequent unseeded calls."""
        import random
        random.seed(0)
        vals_before = [random.random() for _ in range(5)]
        select_difficulty(seed=123)
        random.seed(0)
        vals_after = [random.random() for _ in range(5)]
        assert vals_before == vals_after, "select_difficulty should not mutate global random state"


class TestQuestionTypes:
    def test_easy_returns_foundational_types(self):
        qtype = get_question_type_for_difficulty("easy", seed=1)
        assert qtype in ("conceptual", "practical", "definition")

    def test_hard_returns_advanced_types(self):
        qtype = get_question_type_for_difficulty("hard", seed=1)
        assert qtype in ("theoretical", "research", "synthesis")

    def test_unknown_difficulty_fallback(self):
        qtype = get_question_type_for_difficulty("nonexistent", seed=1)
        assert qtype == "conceptual"


class TestPromptGeneration:
    def test_easy_prompt_contains_topic(self):
        prompt = get_prompt_for_difficulty("algorithms", "easy", "definition")
        assert "algorithms" in prompt
        assert "basic" in prompt.lower() or "simple" in prompt.lower() or "foundational" in prompt.lower()

    def test_hard_prompt_contains_topic(self):
        prompt = get_prompt_for_difficulty("machine learning", "hard", "research")
        assert "machine learning" in prompt
        assert "research" in prompt.lower() or "cutting-edge" in prompt.lower()

    def test_prompt_formatting(self):
        prompt = get_prompt_for_difficulty("quantum mechanics", "medium", "conceptual")
        assert "{topic}" not in prompt, "Prompt should be formatted with topic"


class TestActiveLearningTracker:
    def test_initial_state(self):
        tracker = ActiveLearningTracker()
        assert tracker.get_success_rate("algorithms", "easy") == 0.0

    def test_log_and_retrieve(self):
        tracker = ActiveLearningTracker()
        tracker.log_generation("algorithms", "easy", True, 0.85)
        tracker.log_generation("algorithms", "easy", False, 0.0)
        tracker.log_generation("algorithms", "easy", True, 0.95)
        rate = tracker.get_success_rate("algorithms", "easy")
        assert rate == 2.0 / 3.0

    def test_avg_score_tracking(self):
        tracker = ActiveLearningTracker()
        tracker.log_generation("physics", "medium", True, 0.8)
        tracker.log_generation("physics", "medium", True, 0.9)
        stat = tracker.stats["medium"]["physics"]
        assert stat["avg_score"] == pytest.approx(0.85)

    def test_suggest_adjustment(self):
        tracker = ActiveLearningTracker()
        # Easy has 90% success → should suggest decreasing easy
        for _ in range(10):
            tracker.log_generation("algo", "easy", True, 0.9)
        suggestion = tracker.suggest_difficulty_adjustment()
        assert suggestion["suggested"]["easy"] < DIFFICULTY_DISTRIBUTION["easy"]

    def test_report_output(self):
        tracker = ActiveLearningTracker()
        tracker.log_generation("cs", "easy", True, 0.85)
        report = tracker.report()
        assert "EASY:" in report
        assert "cs:" in report
