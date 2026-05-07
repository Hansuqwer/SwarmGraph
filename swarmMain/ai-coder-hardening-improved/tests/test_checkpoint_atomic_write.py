"""Tests for atomic checkpoint write hardening (C2).

Verifies that:
  - LocalCheckpointStore.save() is atomic (uses temp-file + os.replace)
  - A corrupt checkpoint file raises CheckpointCorrupt, not a raw JSONDecodeError
  - CheckpointNotFound is raised for missing files
"""

from __future__ import annotations

import json
import os
import unittest.mock as mock
from pathlib import Path

import pytest

from src.ai_coder.workflow.checkpoints import (
    CheckpointCorrupt,
    CheckpointNotFound,
    LocalCheckpointStore,
)
from src.ai_coder.workflow.state import WorkflowState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(thread_id: str = "thread-abc") -> WorkflowState:
    return WorkflowState(thread_id=thread_id, task="fix tests", repo_root="/repo")


def _make_store(tmp_path: Path) -> LocalCheckpointStore:
    return LocalCheckpointStore(tmp_path, checkpoint_dir=str(tmp_path / "checkpoints"))


# ---------------------------------------------------------------------------
# Basic save / load round-trip
# ---------------------------------------------------------------------------

class TestCheckpointRoundTrip:
    def test_save_and_load(self, tmp_path):
        store = _make_store(tmp_path)
        state = _make_state()
        state.status = "planning"
        store.save(state)

        loaded = store.load(state.thread_id)
        assert loaded.thread_id == state.thread_id
        assert loaded.task == state.task
        assert loaded.status == "planning"

    def test_checkpoint_file_exists_after_save(self, tmp_path):
        store = _make_store(tmp_path)
        state = _make_state()
        store.save(state)
        assert store.checkpoint_path(state.thread_id).exists()

    def test_checkpoint_is_valid_json(self, tmp_path):
        store = _make_store(tmp_path)
        state = _make_state()
        store.save(state)
        raw = store.checkpoint_path(state.thread_id).read_text()
        data = json.loads(raw)
        assert data["thread_id"] == state.thread_id

    def test_no_tmp_files_left_on_success(self, tmp_path):
        store = _make_store(tmp_path)
        state = _make_state()
        store.save(state)
        tmp_files = list((tmp_path / "checkpoints").glob("*.tmp"))
        assert len(tmp_files) == 0


# ---------------------------------------------------------------------------
# C2: Atomic write — temp-file + os.replace
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_atomic_write_uses_replace(self, tmp_path):
        """Verify os.replace is called (atomic rename pattern)."""
        store = _make_store(tmp_path)
        state = _make_state()
        with mock.patch("os.replace", wraps=os.replace) as mock_replace:
            store.save(state)
        mock_replace.assert_called_once()

    def test_partial_write_failure_cleans_up_tmp(self, tmp_path):
        """If the write fails, the .tmp file should be cleaned up."""
        store = _make_store(tmp_path)
        state = _make_state()
        (tmp_path / "checkpoints").mkdir(parents=True, exist_ok=True)

        original_replace = os.replace

        def failing_replace(src, dst):
            raise OSError("disk full")

        with mock.patch("os.replace", side_effect=failing_replace):
            with pytest.raises(OSError, match="disk full"):
                store.save(state)

        # No .tmp file should remain
        tmp_files = list((tmp_path / "checkpoints").glob("*.tmp"))
        assert len(tmp_files) == 0


# ---------------------------------------------------------------------------
# C2: CheckpointNotFound for missing files
# ---------------------------------------------------------------------------

class TestCheckpointNotFound:
    def test_load_missing_raises_checkpoint_not_found(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(CheckpointNotFound, match="checkpoint not found"):
            store.load("nonexistent-thread")

    def test_raises_checkpoint_not_found_not_file_not_found(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(CheckpointNotFound):
            store.load("missing")
        # Verify it IS a CheckpointNotFound, not a raw FileNotFoundError
        try:
            store.load("missing")
        except CheckpointNotFound:
            pass  # correct
        except FileNotFoundError as e:
            pytest.fail(f"Got raw FileNotFoundError instead of CheckpointNotFound: {e}")


# ---------------------------------------------------------------------------
# C2: CheckpointCorrupt for invalid JSON
# ---------------------------------------------------------------------------

class TestCheckpointCorrupt:
    def test_corrupt_json_raises_checkpoint_corrupt(self, tmp_path):
        store = _make_store(tmp_path)
        (tmp_path / "checkpoints").mkdir(parents=True, exist_ok=True)
        checkpoint_path = store.checkpoint_path("thread-bad")
        checkpoint_path.write_text("{ not valid json !!!")

        with pytest.raises(CheckpointCorrupt, match="corrupt"):
            store.load("thread-bad")

    def test_empty_file_raises_checkpoint_corrupt(self, tmp_path):
        store = _make_store(tmp_path)
        (tmp_path / "checkpoints").mkdir(parents=True, exist_ok=True)
        checkpoint_path = store.checkpoint_path("thread-empty")
        checkpoint_path.write_text("")

        with pytest.raises(CheckpointCorrupt):
            store.load("thread-empty")

    def test_corrupt_does_not_raise_raw_json_error(self, tmp_path):
        store = _make_store(tmp_path)
        (tmp_path / "checkpoints").mkdir(parents=True, exist_ok=True)
        store.checkpoint_path("thread-x").write_text("garbage")
        try:
            store.load("thread-x")
        except CheckpointCorrupt:
            pass  # correct
        except json.JSONDecodeError as e:
            pytest.fail(f"Raw JSONDecodeError leaked out: {e}")
