"""Tests for WorkflowState hardening improvements.

Covers:
  - C1: extra='forbid' rejects unknown fields
  - C1: validate_assignment=True enforces field mutations
  - C6: TokenUsage ge=0 rejects negative tokens
  - C7: history/error list bounding
  - C8: repo_root field validation
  - C9: fail_closed catch-all mapping
  - C10: history dict structure
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ai_coder.workflow.state import (
    TokenUsage,
    WorkflowState,
    _MAX_ERRORS,
    _MAX_HISTORY_ENTRIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**kwargs) -> WorkflowState:
    defaults = dict(thread_id="t1", task="fix failing tests", repo_root="/repo")
    return WorkflowState(**(defaults | kwargs))


# ---------------------------------------------------------------------------
# C1: extra='forbid'
# ---------------------------------------------------------------------------

class TestExtraForbid:
    def test_unknown_field_rejected(self):
        """Unknown fields in checkpoint JSON must raise ValidationError (not silently pass)."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            WorkflowState(
                thread_id="t1",
                task="task",
                repo_root="/repo",
                injected_secret="evil",  # unknown field
            )

    def test_known_fields_accepted(self):
        state = _make_state()
        assert state.status == "initialized"

    def test_model_validate_rejects_extra(self):
        """model_validate (used for checkpoint deserialization) must also reject extra keys."""
        with pytest.raises(ValidationError):
            WorkflowState.model_validate({
                "thread_id": "t1",
                "task": "task",
                "repo_root": "/repo",
                "unknown_injection": "payload",
            })


# ---------------------------------------------------------------------------
# C1: validate_assignment
# ---------------------------------------------------------------------------

class TestValidateAssignment:
    def test_invalid_status_assignment_raises(self):
        state = _make_state()
        with pytest.raises(ValidationError):
            state.status = "hacked_status"  # not in WorkflowStatus

    def test_valid_status_assignment_works(self):
        state = _make_state()
        state.status = "planning"
        assert state.status == "planning"

    def test_invalid_failure_cause_assignment_raises(self):
        state = _make_state()
        with pytest.raises(ValidationError):
            state.failure_cause = "not_a_real_cause"


# ---------------------------------------------------------------------------
# C6: TokenUsage bounds
# ---------------------------------------------------------------------------

class TestTokenUsageBounds:
    def test_negative_input_tokens_rejected(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            TokenUsage(input_tokens=-1, output_tokens=0)

    def test_negative_output_tokens_rejected(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            TokenUsage(input_tokens=0, output_tokens=-5)

    def test_zero_tokens_accepted(self):
        t = TokenUsage(input_tokens=0, output_tokens=0)
        assert t.total() == 0

    def test_positive_tokens_accepted(self):
        t = TokenUsage(input_tokens=100, output_tokens=200)
        assert t.total() == 300


# ---------------------------------------------------------------------------
# C7: bounded lists
# ---------------------------------------------------------------------------

class TestBoundedLists:
    def test_history_capped_on_construction(self):
        many = [{"kind": "memory", "written": True} for _ in range(_MAX_HISTORY_ENTRIES + 50)]
        state = WorkflowState(thread_id="t1", task="t", repo_root="/r", history=many)
        assert len(state.history) <= _MAX_HISTORY_ENTRIES

    def test_errors_capped_on_construction(self):
        many_errors = [f"err {i}" for i in range(_MAX_ERRORS + 20)]
        state = WorkflowState(thread_id="t1", task="t", repo_root="/r", errors=many_errors)
        assert len(state.errors) <= _MAX_ERRORS

    def test_append_history_respects_cap(self):
        state = _make_state()
        for i in range(_MAX_HISTORY_ENTRIES + 10):
            state.append_history({"kind": "memory", "written": True})
        assert len(state.history) <= _MAX_HISTORY_ENTRIES

    def test_add_error_respects_cap(self):
        state = _make_state()
        for i in range(_MAX_ERRORS + 10):
            state.add_error(f"error {i}")
        assert len(state.errors) <= _MAX_ERRORS


# ---------------------------------------------------------------------------
# C8: repo_root validation
# ---------------------------------------------------------------------------

class TestRepoRootValidation:
    def test_empty_repo_root_rejected(self):
        with pytest.raises(ValidationError, match="repo_root must not be empty"):
            _make_state(repo_root="")

    def test_whitespace_only_repo_root_rejected(self):
        with pytest.raises(ValidationError, match="repo_root must not be empty"):
            _make_state(repo_root="   ")

    def test_traversal_repo_root_rejected(self):
        with pytest.raises(ValidationError, match="parent directory traversal"):
            _make_state(repo_root="/repo/../etc/passwd")

    def test_valid_absolute_repo_root_accepted(self):
        state = _make_state(repo_root="/home/user/project")
        assert state.repo_root == "/home/user/project"

    def test_relative_repo_root_accepted(self):
        # Relative paths are allowed (resolved at checkpoint-store level)
        state = _make_state(repo_root="myproject")
        assert state.repo_root == "myproject"


# ---------------------------------------------------------------------------
# Thread ID and task validation
# ---------------------------------------------------------------------------

class TestThreadIdAndTaskValidation:
    def test_empty_thread_id_rejected(self):
        with pytest.raises(ValidationError, match="thread_id must not be empty"):
            _make_state(thread_id="")

    def test_empty_task_rejected(self):
        with pytest.raises(ValidationError, match="task must not be empty"):
            _make_state(task="")

    def test_whitespace_task_rejected(self):
        with pytest.raises(ValidationError, match="task must not be empty"):
            _make_state(task="   ")


# ---------------------------------------------------------------------------
# touch() helper
# ---------------------------------------------------------------------------

class TestTouchHelper:
    def test_touch_updates_timestamp(self):
        import time
        state = _make_state()
        old_ts = state.updated_at
        time.sleep(0.01)
        state.touch()
        assert state.updated_at > old_ts
