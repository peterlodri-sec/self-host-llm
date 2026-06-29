# SPDX-License-Identifier: MIT
"""Tests for upload module — non-destructive, idempotent HF upload."""

import os
import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from ultrawhale.upload import upload_dogfeed


class TestUploadDogfeed:
    def test_dry_run_no_token_needed(self, tmp_path: Path):
        """Dry-run should work without HF_TOKEN."""
        # Create a test JSONL file
        test_file = tmp_path / "dogfeed_test_001.jsonl"
        test_file.write_text('{"id": "1", "user_message": "Q", "free_response": "A"}\n')

        # Make the file old enough to be "not active"
        old_time = time.time() - 3600  # 1 hour ago
        os.utime(test_file, (old_time, old_time))

        with patch("ultrawhale.upload.HfApi") as mock_api:
            mock_api.return_value.list_repo_files.return_value = []
            result = upload_dogfeed(
                tmp_path,
                hf_repo="test/repo",
                hf_token="fake-token",
                active_grace_minutes=0,
                dry_run=True,
            )
            assert result == 0  # dry run, nothing actually uploaded

    def test_empty_directory(self, tmp_path: Path):
        """Empty directory should return 0 with no errors."""
        result = upload_dogfeed(
            tmp_path,
            hf_repo="test/repo",
            hf_token="fake-token",
            dry_run=True,
        )
        assert result == 0

    def test_skips_active_files(self, tmp_path: Path):
        """Files modified recently should be skipped."""
        test_file = tmp_path / "dogfeed_active.jsonl"
        test_file.write_text('{"id": "1", "user_message": "Q", "free_response": "A"}\n')
        # File was just created, so it's "active"

        with patch("ultrawhale.upload.HfApi") as mock_api:
            mock_api.return_value.list_repo_files.return_value = []
            result = upload_dogfeed(
                tmp_path,
                hf_repo="test/repo",
                hf_token="fake-token",
                active_grace_minutes=30,  # Skip files <30 min old
                dry_run=True,
            )
            assert result == 0  # All files skipped

    def test_skips_empty_files(self, tmp_path: Path):
        """Empty files should be skipped."""
        test_file = tmp_path / "dogfeed_empty.jsonl"
        test_file.write_text("")

        with patch("ultrawhale.upload.HfApi") as mock_api:
            mock_api.return_value.list_repo_files.return_value = []
            result = upload_dogfeed(
                tmp_path,
                hf_repo="test/repo",
                hf_token="fake-token",
                active_grace_minutes=0,
                dry_run=True,
            )
            assert result == 0

    def test_nonexistent_directory_errors(self, tmp_path: Path):
        """Non-existent directory should exit with error."""
        with pytest.raises(SystemExit):
            upload_dogfeed(
                tmp_path / "does_not_exist",
                hf_repo="test/repo",
                hf_token="fake-token",
                dry_run=True,
            )
