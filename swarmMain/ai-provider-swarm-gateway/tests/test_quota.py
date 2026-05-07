"""Tests for quota tracker — conservative, append-only, reset-aware."""
from __future__ import annotations
import pytest
import tempfile
from pathlib import Path
from src.ai_provider_swarm_gateway.quota.tracker import QuotaTracker


@pytest.fixture
def tracker(tmp_path):
    return QuotaTracker(storage_path=tmp_path / "usage.json")


class TestQuotaTracker:
    def test_initial_usage_is_zero(self, tracker):
        u = tracker.get_usage("groq")
        assert u.used_requests == 0
        assert u.used_tokens == 0

    def test_increment_adds_correctly(self, tracker):
        tracker.increment("groq", requests=5, tokens=1000)
        u = tracker.get_usage("groq")
        assert u.used_requests == 5
        assert u.used_tokens == 1000

    def test_increment_is_cumulative(self, tracker):
        tracker.increment("groq", requests=3, tokens=100)
        tracker.increment("groq", requests=2, tokens=200)
        u = tracker.get_usage("groq")
        assert u.used_requests == 5
        assert u.used_tokens == 300

    def test_cannot_decrement(self, tracker):
        with pytest.raises(ValueError, match="Cannot decrement"):
            tracker.increment("groq", requests=-1)

    def test_is_exhausted_when_at_limit(self, tracker):
        tracker.increment("groq", requests=100)
        assert tracker.is_exhausted("groq", max_requests=100) is True

    def test_not_exhausted_below_limit(self, tracker):
        tracker.increment("groq", requests=50)
        assert tracker.is_exhausted("groq", max_requests=100) is False

    def test_unknown_limit_never_exhausted(self, tracker):
        tracker.increment("groq", requests=99999)
        assert tracker.is_exhausted("groq", max_requests=None) is False

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "usage.json"
        t1 = QuotaTracker(storage_path=path)
        t1.increment("groq", requests=7)
        t2 = QuotaTracker(storage_path=path)
        u = t2.get_usage("groq")
        assert u.used_requests == 7

    def test_all_usage_returns_all_providers(self, tracker):
        tracker.increment("groq", requests=5)
        tracker.increment("mistral", requests=3)
        all_u = tracker.all_usage()
        assert any("groq" in k for k in all_u)
        assert any("mistral" in k for k in all_u)

    def test_quota_exhaustion_blocks_provider(self, tracker):
        tracker.increment("cerebras", requests=1000)
        assert tracker.is_exhausted("cerebras", max_requests=1000) is True

    def test_unknown_provider_limits_are_not_treated_as_free(self, tracker):
        """Key policy test: unknown limit must not claim exhaustion — caller decides conservatively."""
        u = tracker.get_usage("unknown_provider")
        assert u.used_requests == 0
        # is_exhausted with None limit returns False — policy layer handles the rest
        assert tracker.is_exhausted("unknown_provider", max_requests=None) is False
