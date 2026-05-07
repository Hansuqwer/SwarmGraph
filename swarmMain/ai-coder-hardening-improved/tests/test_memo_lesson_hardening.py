"""Tests for MemoLesson hardening improvements (C4 — expanded metachar denylist).

Verifies that every unsafe_summary_examples() case is rejected,
and that legitimate summaries are accepted.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ai_coder.memory.lesson import MemoLesson, unsafe_summary_examples


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lesson(**kwargs) -> MemoLesson:
    defaults = dict(
        rule_kind="test_runner",
        file_glob="tests/*.py",
        summary="Always run pytest with the -x flag for fail-fast behaviour.",
        review_passed=True,
    )
    return MemoLesson(**(defaults | kwargs))


# ---------------------------------------------------------------------------
# Valid lessons
# ---------------------------------------------------------------------------

class TestValidLessons:
    def test_basic_lesson_accepted(self):
        lesson = _make_lesson()
        assert lesson.rule_kind == "test_runner"

    def test_all_rule_kinds_accepted(self):
        for kind in ("test_runner", "patch_validator", "security_guard", "style_guide"):
            lesson = _make_lesson(rule_kind=kind)
            assert lesson.rule_kind == kind

    def test_key_returns_tuple(self):
        lesson = _make_lesson(file_glob="src/**/*.py")
        assert lesson.key() == ("test_runner", "src/**/*.py")

    def test_frozen_model_cannot_be_mutated(self):
        lesson = _make_lesson()
        with pytest.raises(Exception):  # ValidationError or TypeError depending on pydantic
            lesson.summary = "new summary"  # type: ignore


# ---------------------------------------------------------------------------
# Summary metachar denylist (C4)
# ---------------------------------------------------------------------------

class TestUnsafeSummaries:
    @pytest.mark.parametrize("bad_summary", unsafe_summary_examples())
    def test_unsafe_summary_rejected(self, bad_summary: str):
        with pytest.raises(ValidationError):
            _make_lesson(summary=bad_summary)

    def test_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="run; rm -rf /")

    def test_pipe_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="cat file | grep secret")

    def test_backtick_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="run `command`")

    def test_dollar_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="echo $HOME")

    # C4 additions
    def test_bang_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="run !! again")

    def test_subshell_open_paren_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="run (subshell)")

    def test_brace_expansion_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="use {a,b} pattern")

    def test_newline_injection_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="line1\nline2")

    def test_carriage_return_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="line1\r\nline2")

    def test_url_http_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="see http://example.com for details")

    def test_url_https_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(summary="see https://example.com for details")


# ---------------------------------------------------------------------------
# file_glob validation
# ---------------------------------------------------------------------------

class TestFileGlobValidation:
    def test_absolute_glob_rejected(self):
        with pytest.raises(ValidationError, match="relative"):
            _make_lesson(file_glob="/absolute/path/*.py")

    def test_parent_traversal_rejected(self):
        with pytest.raises(ValidationError, match="parent traversal"):
            _make_lesson(file_glob="../etc/passwd")

    def test_valid_relative_glob_accepted(self):
        lesson = _make_lesson(file_glob="src/**/*.py")
        assert lesson.file_glob == "src/**/*.py"

    def test_wildcard_glob_accepted(self):
        lesson = _make_lesson(file_glob="*.py")
        assert lesson.file_glob == "*.py"

    def test_shell_injection_in_glob_rejected(self):
        with pytest.raises(ValidationError):
            _make_lesson(file_glob="src/*.py; rm -rf /")


# ---------------------------------------------------------------------------
# review_passed constraint
# ---------------------------------------------------------------------------

class TestReviewPassed:
    def test_review_not_passed_rejected(self):
        with pytest.raises(ValidationError, match="approved runs"):
            _make_lesson(review_passed=False)

    def test_review_passed_true_accepted(self):
        lesson = _make_lesson(review_passed=True)
        assert lesson.review_passed is True
