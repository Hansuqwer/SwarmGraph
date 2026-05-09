"""SwarmMemory tests."""

import json
from pathlib import Path

import pytest
from swarm.models.memory import SwarmMemory, SwarmMemoryEntry


def test_store_and_get():
    m = SwarmMemory()
    e = m.store("k1", "value 1", namespace="ns1")
    assert m.get("k1", "ns1") == e


def test_store_replaces_existing_key():
    m = SwarmMemory()
    m.store("k1", "v1", namespace="ns")
    m.store("k1", "v2", namespace="ns")
    assert m.get("k1", "ns").value == "v2"
    assert m.size() == 1


def test_promote_score_preserves_created_at():
    """F-26B: promote_score must not reset created_at."""
    m = SwarmMemory()
    m.store("k1", "v1", namespace="ns", score=0.5)
    original_ts = m.get("k1", "ns").created_at
    m.promote_score("k1", "ns", delta=0.2)
    new_entry = m.get("k1", "ns")
    assert new_entry.score == 0.7
    assert new_entry.created_at == original_ts


def test_distill_removes_low_score_entries():
    m = SwarmMemory(sona_min_score=0.7)
    m.store("k_high", "v_high", score=0.9)
    m.store("k_low", "v_low", score=0.4)
    removed = m.distill()
    assert len(removed) == 1
    assert m.get("k_low") is None
    assert m.get("k_high") is not None


def test_search_uses_namespace_index(basic_state=None):
    m = SwarmMemory()
    m.store("py-list", "list comprehension", namespace="python")
    m.store("js-array", "array.map", namespace="javascript")
    results = m.search("comprehension", namespace="python")
    assert len(results) == 1
    assert results[0].namespace == "python"


def test_export_import_jsonl_round_trip(tmp_path: Path):
    """F-26A: persistence."""
    m1 = SwarmMemory()
    m1.store("k1", "v1", namespace="ns", score=0.9)
    m1.store("k2", "v2", namespace="ns", score=0.8)
    fp = tmp_path / "mem.jsonl"
    count = m1.export_jsonl(fp)
    assert count == 2

    m2 = SwarmMemory()
    loaded = m2.import_jsonl(fp, replace=True)
    assert loaded == 2
    assert m2.get("k1", "ns").value == "v1"
    assert m2.get("k2", "ns").value == "v2"


def test_cap_evicts_lowest_score():
    m = SwarmMemory(max_entries=3)
    m.store("k1", "v1", score=0.9)
    m.store("k2", "v2", score=0.5)
    m.store("k3", "v3", score=0.1)
    m.store("k4", "v4", score=0.95)
    # k3 (lowest score) should be evicted
    assert m.get("k3") is None
    assert m.size() == 3


def test_index_is_private_attr():
    """F-12A: _index does not appear in model_dump."""
    m = SwarmMemory()
    m.store("k1", "v1")
    dumped = m.model_dump()
    assert "_index" not in dumped


def test_memory_construction_caps():
    """F-12-T1: cap enforced on construction."""
    entries = [
        SwarmMemoryEntry(key=f"k{i}", value=f"v{i}", score=1.0 - i * 0.01) for i in range(50)
    ]
    m = SwarmMemory(entries=entries, max_entries=10)
    assert m.size() == 10
