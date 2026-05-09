"""F-29A + F-29B + F-29-PERF1 + F-29-LG1 verification."""

import json
import os
from pathlib import Path

import pytest

# This test only exercises the patched tracker.py. It does NOT require the
# rest of the gateway to be importable (the rest needs files we couldn't fetch).


def test_tracker_storage_path_injectable(tmp_path: Path):
    """F-29-LG1."""
    from ai_provider_swarm_gateway.quota.tracker import QuotaTracker

    custom = tmp_path / "custom_usage.json"
    t = QuotaTracker(storage_path=custom)
    t.increment("openai", requests=1)
    assert custom.exists()


def test_tracker_atomic_write_no_temp_files_left(tmp_path: Path):
    """F-29A: tempfile cleanup."""
    from ai_provider_swarm_gateway.quota.tracker import QuotaTracker

    t = QuotaTracker(storage_path=tmp_path / "usage.json")
    t.increment("openai", requests=5, tokens=100)
    leftover = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftover == []


def test_tracker_increment_persists(tmp_path: Path):
    from ai_provider_swarm_gateway.quota.tracker import QuotaTracker

    fp = tmp_path / "usage.json"
    t1 = QuotaTracker(storage_path=fp)
    t1.increment("openai", requests=3, tokens=50)
    # New tracker reads from disk
    t2 = QuotaTracker(storage_path=fp)
    usage = t2.get_usage("openai")
    assert usage.used_requests == 3
    assert usage.used_tokens == 50


def test_tracker_rejects_negative_increment(tmp_path: Path):
    from ai_provider_swarm_gateway.quota.tracker import QuotaTracker

    t = QuotaTracker(storage_path=tmp_path / "usage.json")
    with pytest.raises(ValueError):
        t.increment("openai", requests=-1)
    with pytest.raises(ValueError):
        t.increment("openai", tokens=-1)


def test_tracker_concurrent_increments_no_loss(tmp_path: Path):
    """F-29B: serial calls within a single process should never lose updates.

    True multi-process testing requires forking; here we verify the in-process
    invariant under tight loops (the lock serialises reads + writes).
    """
    from ai_provider_swarm_gateway.quota.tracker import QuotaTracker

    fp = tmp_path / "usage.json"
    t = QuotaTracker(storage_path=fp)
    for _ in range(50):
        t.increment("openai", requests=1, tokens=10)
    final = t.get_usage("openai")
    assert final.used_requests == 50
    assert final.used_tokens == 500


def test_tracker_lazy_load(tmp_path: Path):
    """F-29-PERF1: nothing happens until the first get_usage / increment."""
    from ai_provider_swarm_gateway.quota.tracker import QuotaTracker

    fp = tmp_path / "usage.json"
    t = QuotaTracker(storage_path=fp)
    # No file accesses yet
    assert not fp.exists()
    # First call materialises
    t.get_usage("openai")
    # Read-only: still no file
    assert not fp.exists()
    # Increment writes
    t.increment("openai", requests=1)
    assert fp.exists()


def test_tracker_handles_corrupt_json_gracefully(tmp_path: Path):
    """If the storage file is corrupt, treat as empty (and atomic writes prevent
    further corruption going forward)."""
    from ai_provider_swarm_gateway.quota.tracker import QuotaTracker

    fp = tmp_path / "usage.json"
    fp.write_text("{not json at all}")
    t = QuotaTracker(storage_path=fp)
    usage = t.get_usage("openai")
    # Corrupt file → treated as empty
    assert usage.used_requests == 0
    # Subsequent writes succeed atomically
    t.increment("openai", requests=1)
    # File is now valid JSON
    data = json.loads(fp.read_text())
    assert "openai:daily" in data
