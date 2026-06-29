# SPDX-License-Identifier: MIT
"""Post-processing: compress generated Q&A pairs with kompress-v8."""

import json
from typing import Optional

from ultrawhale.config import Config
from ultrawhale.logging import get_logger

logger = get_logger("kompress")

try:
    from huggingface_hub import InferenceClient
except ImportError:
    logger.error("huggingface_hub not installed. Run: pip install huggingface_hub")
    raise


class KompressClient:
    """Wrapper for kompress-v8 (context pruner/compressor)."""

    MODEL = "PeetPedro/kompress-v8"

    def __init__(self, api_token: Optional[str] = None):
        self.token = api_token or Config().hf_token
        if not self.token:
            raise ValueError("HF_TOKEN not set — kompress requires HuggingFace authentication")
        self.client = InferenceClient(api_key=self.token)

    def compress_text(self, text: str, max_tokens: int = 200) -> Optional[str]:
        """Compress text using kompress-v8."""
        try:
            prompt = f"Compress this concisely (max {max_tokens} tokens):\n{text}"
            response = self.client.text_generation(
                prompt,
                model=self.MODEL,
                max_new_tokens=max_tokens,
                temperature=0.3,
            )
            return response.strip() if response else None
        except Exception as e:
            logger.warning(f"Compression failed: {e}")
            return None

    def compress_qa_pair(self, question: str, answer: str) -> dict:
        """Compress Q&A pair; keep originals if compression fails."""
        q_compressed = self.compress_text(question, max_tokens=80)
        a_compressed = self.compress_text(answer, max_tokens=150)

        return {
            "question": q_compressed or question,
            "answer": a_compressed or answer,
            "compressed": bool(q_compressed and a_compressed),
        }


def compress_jsonl_file(input_file: str, output_file: str, api_token: Optional[str] = None) -> int:
    """Compress all Q&A pairs in a JSONL file.

    Args:
        input_file: Path to input JSONL.
        output_file: Path to output JSONL.
        api_token: Optional HF token override.

    Returns:
        Number of pairs successfully compressed.
    """
    try:
        kompressor = KompressClient(api_token)
    except ValueError as e:
        logger.error(str(e))
        return 0

    compressed_count = 0
    total_count = 0

    try:
        with open(input_file) as inf, open(output_file, "w") as outf:
            for line in inf:
                if not line.strip():
                    continue

                total_count += 1
                try:
                    pair = json.loads(line)

                    compressed = kompressor.compress_qa_pair(
                        pair.get("user_message", ""),
                        pair.get("free_response", ""),
                    )

                    if compressed["compressed"]:
                        pair["user_message"] = compressed["question"]
                        pair["free_response"] = compressed["answer"]
                        pair["kompressed_at"] = True
                        compressed_count += 1

                    outf.write(json.dumps(pair) + "\n")

                    if total_count % 10 == 0:
                        logger.info(f"{total_count} processed, {compressed_count} compressed")

                except json.JSONDecodeError:
                    logger.warning(f"Skipped invalid JSON at line {total_count}")

    except OSError as e:
        logger.error(f"File processing failed: {e}")
        return compressed_count

    logger.info(f"Compression complete: {compressed_count}/{total_count} pairs compressed")
    return compressed_count


if __name__ == "__main__":
    import argparse
    import sys as _sys

    parser = argparse.ArgumentParser(description="Compress Q&A pairs with kompress-v8")
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("--output", help="Output JSONL file (default: input_kompressed.jsonl)")
    parser.add_argument("--token", help="HF_TOKEN override")

    args = parser.parse_args()
    output = args.output or args.input.replace(".jsonl", "_kompressed.jsonl")

    count = compress_jsonl_file(args.input, output, args.token)
    _sys.exit(0 if count >= 0 else 1)
