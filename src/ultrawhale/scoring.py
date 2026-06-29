# SPDX-License-Identifier: MIT
"""Quality scoring for generated Q&A pairs.

Deterministic scoring functions for coherence, length, diversity, and
final quality — all pure functions with no side effects.
"""

import hashlib
from typing import Tuple


# Default quality thresholds (overridable via Config)
QUALITY_THRESHOLDS = {
    "min_question_tokens": 8,
    "max_question_tokens": 200,
    "min_answer_tokens": 20,
    "max_answer_tokens": 2000,
    "min_score": 0.65,
}

# Global deduplication set (scoped to process lifetime)
_seen_hashes: set[str] = set()


def reset_seen_hashes() -> None:
    """Clear the deduplication hash set (useful for testing)."""
    global _seen_hashes
    _seen_hashes = set()


def token_count(text: str) -> int:
    """Rough token estimate: split on whitespace."""
    return len(text.split())


def calculate_quality_score(question: str, answer: str, topic: str = "") -> Tuple[float, dict]:
    """Score a Q&A pair on coherence, length, and diversity (0.0–1.0).

    Args:
        question: The generated question text.
        answer: The generated answer text.
        topic: Topic category (unused in scoring, reserved for future weighting).

    Returns:
        Tuple of (final_score, score_breakdown_dict).
    """
    scores: dict[str, float] = {}

    q_tokens = token_count(question)
    a_tokens = token_count(answer)

    q_len = 1.0 if (QUALITY_THRESHOLDS["min_question_tokens"] <= q_tokens <= QUALITY_THRESHOLDS["max_question_tokens"]) else 0.3
    a_len = 1.0 if (QUALITY_THRESHOLDS["min_answer_tokens"] <= a_tokens <= QUALITY_THRESHOLDS["max_answer_tokens"]) else 0.4

    length_score = (q_len * 0.4) + (a_len * 0.6)
    scores["length"] = length_score

    has_punctuation = any(p in question for p in "?.!;:") and any(p in answer for p in ".!;:")
    coherence_score = 0.9 if has_punctuation else 0.7
    coherence_score *= 1.0 if len(answer) > len(question) else 0.8
    scores["coherence"] = min(coherence_score, 1.0)

    q_hash = hashlib.md5((question + answer).encode()).hexdigest()
    is_novel = q_hash not in _seen_hashes
    diversity_score = 1.0 if is_novel else 0.1
    scores["diversity"] = diversity_score

    if is_novel:
        _seen_hashes.add(q_hash)

    final_score = (length_score * 0.35) + (coherence_score * 0.35) + (diversity_score * 0.30)

    return min(final_score, 1.0), scores
