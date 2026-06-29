#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Curation Engine: Judge, Verify, and Diversify Q&A pairs.

Migrated from self-host-llm/curation_engine.py into the ultrawhale package.
"""

from typing import Any, Dict, Optional

from ultrawhale.hf import HFInferenceClient
from ultrawhale.logging import get_logger

logger = get_logger("curation")


class CurationEngine:
    """Engine to curate Q&A pairs using LLM-as-a-Judge and code execution verification.

    The engine wraps :class:`HFInferenceClient` for LLM-based judgement and
    sandboxed code verification for Q&A pairs that contain code blocks.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        """Initialize the curation engine.

        Args:
            token: Optional HuggingFace API token. Falls back to the
                   project-wide :class:`Config` default.
        """
        self.client: HFInferenceClient = HFInferenceClient(api_token=token)
        logger.info("CurationEngine initialised")

    # ------------------------------------------------------------------
    # Judgement
    # ------------------------------------------------------------------

    def judge_pair(self, qa_pair: Dict[str, Any]) -> float:
        """Rate a Q&A pair for accuracy and quality on a scale of 1-5.

        Uses LLM-as-a-Judge via the HF Inference API. On any failure the
        pair receives a neutral score of 3.0 so it is not silently rejected.

        Args:
            qa_pair: Dictionary containing ``'user_message'`` and
                     ``'free_response'`` keys.

        Returns:
            A float score between 1.0 and 5.0. Defaults to 3.0 on failure.
        """
        question = qa_pair.get("user_message", "")
        answer = qa_pair.get("free_response", "")
        prompt = (
            f"Rate this Q&A pair for accuracy and quality (1-5). "
            f"Output only the number.\n"
            f"Q: {question}\n"
            f"A: {answer}"
        )
        logger.debug("Judging Q&A pair (question length=%d)", len(question))
        score_str: Optional[str] = self.client._chat(
            [{"role": "user", "content": prompt}], "llama70b", max_tokens=10
        )
        try:
            score = float(score_str.strip()) if score_str else 3.0
        except (ValueError, AttributeError):
            score = 3.0

        logger.info("Q&A pair judged — score=%.1f", score)
        return score

    # ------------------------------------------------------------------
    # Code verification
    # ------------------------------------------------------------------

    def verify_code(self, qa_pair: Dict[str, Any]) -> bool:
        """Verify Python code snippets via sandboxed execution.

        Currently a placeholder: logs a warning when Python code blocks are
        detected and returns ``True``.  A future revision should execute the
        snippet in a containerised sandbox and capture the result.

        Args:
            qa_pair: Dictionary containing the Q&A content (checked for
                     ``'free_response'`` with a `````python`` code fence).

        Returns:
            Always ``True`` in this revision.
        """
        answer = qa_pair.get("free_response", "")
        if "```python" in answer:
            logger.warning(
                "Code execution verification: PENDING — snippet detected "
                "but sandbox is not yet wired. Pair accepted tentatively."
            )
        return True

    # ------------------------------------------------------------------
    # Full curation pipeline
    # ------------------------------------------------------------------

    def curate(self, qa_pair: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run the full curation pipeline (judgement then code verification).

        ``judge_pair`` is called first. If the score is below the
        ``curation_threshold`` (4.0), the pair is rejected.  Pairs that pass
        are then run through ``verify_code``.

        Args:
            qa_pair: Raw Q&A pair to be evaluated.  Must contain at least
                     ``'user_message'`` and ``'free_response'``.

        Returns:
            The original ``qa_pair`` dict with the key ``'curated_score'``
            added if the pair passes both phases, or ``None`` if rejected.
        """
        score: float = self.judge_pair(qa_pair)

        if score < 4.0:
            logger.info(
                "Pair rejected — score %.1f below threshold 4.0", score
            )
            return None

        if not self.verify_code(qa_pair):
            logger.info("Pair rejected — code verification failed")
            return None

        qa_pair["curated_score"] = score
        logger.info("Pair accepted — curated_score=%.1f", score)
        return qa_pair
