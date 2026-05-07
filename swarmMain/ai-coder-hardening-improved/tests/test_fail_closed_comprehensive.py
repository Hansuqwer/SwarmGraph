"""Tests for fail_closed() comprehensive mapping (C9).

Verifies:
  - All known ModelGateway exception types map to correct failure_cause
  - Unknown exceptions map to 'unknown' (never leaves failure_cause unset)
  - Error messages are redacted before being stored in model_errors
"""

from __future__ import annotations

import unittest.mock as mock

import pytest

from src.ai_coder.workflow.state import WorkflowState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state() -> WorkflowState:
    return WorkflowState(thread_id="t1", task="task", repo_root="/repo")


def _make_fail_closed():
    """Import fail_closed with mocked model error classes."""
    # We mock the model error classes since they're optional dependencies
    class FakeAuthError(Exception): pass
    class FakeRateLimited(Exception): pass
    class FakeUnavailable(Exception): pass
    class FakeOutputInvalid(Exception): pass
    class FakeGatewayError(Exception): pass

    with mock.patch(
        "src.ai_coder.workflow.nodes._get_model_errors",
        return_value=(FakeAuthError, FakeGatewayError, FakeRateLimited, FakeUnavailable, FakeOutputInvalid),
    ):
        from src.ai_coder.workflow.nodes import fail_closed
        return fail_closed, FakeAuthError, FakeRateLimited, FakeUnavailable, FakeOutputInvalid, FakeGatewayError


# ---------------------------------------------------------------------------
# fail_closed tests
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_auth_error_maps_to_auth_failed(self):
        fail_closed, AuthError, *_ = _make_fail_closed()
        state = _make_state()
        result = fail_closed(state, AuthError("auth failed"))
        assert result.status == "model_unavailable"
        assert result.failure_cause == "auth_failed"

    def test_rate_limited_maps_correctly(self):
        fail_closed, _, RateLimited, *_ = _make_fail_closed()
        state = _make_state()
        result = fail_closed(state, RateLimited("too many requests"))
        assert result.status == "model_unavailable"
        assert result.failure_cause == "rate_limited"

    def test_unavailable_maps_to_gateway_unavailable(self):
        fail_closed, _, _, Unavailable, *_ = _make_fail_closed()
        state = _make_state()
        result = fail_closed(state, Unavailable("service down"))
        assert result.status == "model_unavailable"
        assert result.failure_cause == "gateway_unavailable"

    def test_output_invalid_maps_correctly(self):
        fail_closed, _, _, _, OutputInvalid, _ = _make_fail_closed()
        state = _make_state()
        result = fail_closed(state, OutputInvalid("bad JSON"))
        assert result.status == "failed"
        assert result.failure_cause == "output_invalid"

    def test_unknown_exception_maps_to_unknown(self):
        """C9: Unexpected exceptions must map to 'unknown', not leave failure_cause=None."""
        fail_closed, *_ = _make_fail_closed()
        state = _make_state()
        result = fail_closed(state, RuntimeError("something unexpected"))
        assert result.failure_cause == "unknown"
        assert result.status == "failed"

    def test_failure_cause_never_none_after_fail_closed(self):
        """failure_cause must always be set after fail_closed — never None."""
        fail_closed, *_ = _make_fail_closed()
        for exc in [
            RuntimeError("oops"),
            ValueError("bad value"),
            KeyError("missing key"),
            MemoryError("oom"),
        ]:
            state = _make_state()
            result = fail_closed(state, exc)
            assert result.failure_cause is not None, (
                f"failure_cause was None after fail_closed with {type(exc).__name__}"
            )

    def test_error_message_is_added_to_model_errors(self):
        fail_closed, *_ = _make_fail_closed()
        state = _make_state()
        fail_closed(state, RuntimeError("test error"))
        assert len(state.model_errors) > 0

    def test_sensitive_error_message_is_redacted(self):
        """Secrets in error messages must be redacted before storage."""
        fail_closed, *_ = _make_fail_closed()
        state = _make_state()
        # Simulate an exception message containing an API key pattern
        fail_closed(state, RuntimeError("error: token=sk-abc123secret"))
        # The model error should not contain the raw secret
        for msg in state.model_errors:
            assert "sk-abc123secret" not in msg or "[REDACTED]" in msg
