"""Regression tests for v7.1 canonicalization fixes (gateway side).

Covered:
  - F-29-CORR1: QuotaTracker.reset_usage MUST zero on-disk state, not
                merge with disk state (which would preserve the higher
                of in-memory zero vs on-disk N).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── F-29-CORR1: reset_usage is authoritative ────────────────────────────

def _make_tracker(tmp_path: Path, monkeypatch):
    """Produce a fresh QuotaTracker with a tmp HOME so we don't touch user data."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AI_PROVIDER_GATEWAY_TENANT", raising=False)
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod
    importlib.reload(tracker_mod)
    return tracker_mod


def test_reset_usage_zeros_after_increment(tmp_path: Path, monkeypatch):
    """The headline bug: increment to N, reset, then read should give 0.

    Pre-F-29-CORR1: reset wrote {used_requests: 0} in-memory, then
    _save_locked merged with on-disk via max(in_memory, on_disk) → 0
    became max(0, N) = N. Reset was silently swallowed.
    """
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    t = tracker_mod.QuotaTracker.for_tenant("alice")

    t.increment("openai", requests=10, tokens=500)
    assert t.get_usage("openai").used_requests == 10
    assert t.get_usage("openai").used_tokens == 500

    after_reset = t.reset_usage("openai")
    assert after_reset.used_requests == 0, (
        "F-29-CORR1 regression: reset_usage did not zero used_requests. "
        f"Got {after_reset.used_requests} (expected 0)."
    )
    assert after_reset.used_tokens == 0, (
        "F-29-CORR1 regression: reset_usage did not zero used_tokens. "
        f"Got {after_reset.used_tokens} (expected 0)."
    )


def test_reset_usage_writes_zero_to_disk(tmp_path: Path, monkeypatch):
    """The on-disk file must show 0 after reset, not the previous value."""
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    t = tracker_mod.QuotaTracker.for_tenant("alice")
    t.increment("openai", requests=42, tokens=100)
    t.reset_usage("openai")

    on_disk = json.loads(t.storage_path.read_text())
    entry = on_disk["openai:daily"]
    assert entry["used_requests"] == 0, (
        f"F-29-CORR1 regression: on-disk used_requests = {entry['used_requests']}, "
        "expected 0. The merge-with-disk path swallowed the reset."
    )
    assert entry["used_tokens"] == 0


def test_reset_usage_does_not_affect_other_providers(tmp_path: Path, monkeypatch):
    """Reset must be scoped to the named provider, not global."""
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    t = tracker_mod.QuotaTracker.for_tenant("alice")
    t.increment("openai", requests=10)
    t.increment("anthropic", requests=20)
    t.reset_usage("openai")

    assert t.get_usage("openai").used_requests == 0
    assert t.get_usage("anthropic").used_requests == 20  # untouched


def test_reset_usage_does_not_affect_other_windows(tmp_path: Path, monkeypatch):
    """Reset must be scoped to the named (provider, window) pair."""
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    t = tracker_mod.QuotaTracker.for_tenant("alice")
    t.increment("openai", requests=10, window="daily")
    t.increment("openai", requests=5, window="monthly")
    t.reset_usage("openai", window="daily")

    assert t.get_usage("openai", window="daily").used_requests == 0
    assert t.get_usage("openai", window="monthly").used_requests == 5  # untouched


def test_reset_usage_then_increment_starts_from_zero(tmp_path: Path, monkeypatch):
    """After reset → increment, counter must equal the increment amount, not previous + increment."""
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    t = tracker_mod.QuotaTracker.for_tenant("alice")
    t.increment("openai", requests=100)
    t.reset_usage("openai")
    t.increment("openai", requests=3)
    assert t.get_usage("openai").used_requests == 3


def test_reset_usage_idempotent(tmp_path: Path, monkeypatch):
    """Calling reset twice in a row stays at zero (no underflow, no error)."""
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    t = tracker_mod.QuotaTracker.for_tenant("alice")
    t.increment("openai", requests=10)
    t.reset_usage("openai")
    t.reset_usage("openai")
    assert t.get_usage("openai").used_requests == 0


def test_reset_usage_isolated_per_tenant(tmp_path: Path, monkeypatch):
    """Reset on alice must not touch bob's counter."""
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    alice = tracker_mod.QuotaTracker.for_tenant("alice")
    bob = tracker_mod.QuotaTracker.for_tenant("bob")
    alice.increment("openai", requests=10)
    bob.increment("openai", requests=10)

    alice.reset_usage("openai")

    assert alice.get_usage("openai").used_requests == 0
    assert bob.get_usage("openai").used_requests == 10  # F-29-CORR1 + tenant isolation


def test_reset_usage_clears_reset_at(tmp_path: Path, monkeypatch):
    """reset_usage should also clear any scheduled reset_at timestamp."""
    from datetime import datetime, timedelta, timezone
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    t = tracker_mod.QuotaTracker.for_tenant("alice")
    t.increment("openai", requests=10)
    t.set_reset_time("openai", datetime.now(tz=timezone.utc) + timedelta(hours=1))

    t.reset_usage("openai")

    after = t.get_usage("openai")
    assert after.used_requests == 0
    assert after.reset_at is None


# ── CLI integration: reset via the gateway CLI command works too ────────

def test_cli_quota_reset_zeros_actual_disk_state(tmp_path: Path, monkeypatch):
    """End-to-end: invoke the CLI 'quota reset' command, then read on disk."""
    tracker_mod = _make_tracker(tmp_path, monkeypatch)
    from typer.testing import CliRunner
    from ai_provider_swarm_gateway.cli import app

    runner = CliRunner()

    runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai",
         "--requests", "7", "--tenant", "alice"],
    )
    runner.invoke(
        app,
        ["quota", "reset", "--provider", "openai", "--yes", "--tenant", "alice"],
    )

    # Read the file directly
    fp = tracker_mod.QuotaTracker.tenant_storage_path("alice")
    assert fp.exists()
    on_disk = json.loads(fp.read_text())
    assert on_disk["openai:daily"]["used_requests"] == 0, (
        "F-29-CORR1 regression via CLI: 'quota reset' did not zero on-disk state."
    )
