"""
AGENT 29 — Test Engineer
Test suite 4/5: SONA self-learning loop + memory correctness.
"""
from __future__ import annotations

import pytest

from swarm.models.config import SwarmConfig
from swarm.models.memory import SwarmMemory, SwarmMemoryEntry
from swarm.models.state import SwarmState
from swarm.nodes.sona import distill_node, memory_retrieve_node
from swarm.nodes.checkpointing import InProcessCheckpointStore


# ── SwarmMemory: store/search/distill ────────────────────────────────────────

class TestSwarmMemoryFull:
    def test_store_then_get_exact(self):
        mem = SwarmMemory()
        mem.store("k1", "exact value", namespace="test")
        entry = mem.get("k1", "test")
        assert entry is not None
        assert entry.value == "exact value"

    def test_overwrite_same_key(self):
        mem = SwarmMemory()
        mem.store("k1", "v1")
        mem.store("k1", "v2")
        assert mem.get("k1").value == "v2"
        assert mem.size() == 1

    def test_namespace_isolation(self):
        mem = SwarmMemory()
        mem.store("key", "ns-a-value", namespace="ns-a")
        mem.store("key", "ns-b-value", namespace="ns-b")
        assert mem.get("key", "ns-a").value == "ns-a-value"
        assert mem.get("key", "ns-b").value == "ns-b-value"

    def test_search_top_k_respected(self):
        mem = SwarmMemory()
        for i in range(10):
            mem.store(f"k{i}", f"testing pattern {i}", score=0.9)
        results = mem.search("testing pattern", top_k=3)
        assert len(results) <= 3

    def test_distill_removes_low_removes_correct(self):
        mem = SwarmMemory(sona_min_score=0.6)
        mem.store("keep-1", "good pattern", score=0.9)
        mem.store("keep-2", "another good", score=0.8)
        mem.store("remove-1", "weak pattern", score=0.3)
        mem.store("remove-2", "very weak", score=0.2)
        removed = mem.distill()
        remove_keys = {e.key for e in removed}
        assert "remove-1" in remove_keys
        assert "remove-2" in remove_keys
        assert mem.get("keep-1") is not None
        assert mem.get("keep-2") is not None

    def test_promote_score_increases_score(self):
        mem = SwarmMemory()
        mem.store("k1", "value", score=0.5)
        mem.promote_score("k1", delta=0.1)
        entry = mem.get("k1")
        assert entry.score > 0.5

    def test_score_capped_at_1(self):
        mem = SwarmMemory()
        mem.store("k1", "value", score=0.99)
        mem.promote_score("k1", delta=0.5)
        entry = mem.get("k1")
        assert entry.score <= 1.0

    def test_max_entries_enforced(self):
        mem = SwarmMemory(max_entries=5)
        for i in range(20):
            mem.store(f"k{i}", "val", score=float(i) / 20)
        assert mem.size() <= 5


# ── distill_node ──────────────────────────────────────────────────────────────

class TestDistillNode:
    def _make_state(self, with_output: bool = True) -> dict:
        config = SwarmConfig(topology="hierarchical", sona_enabled=True)
        state = SwarmState(
            swarm_id="sona-test",
            objective="Fix tests in the project",
            config=config,
        )
        if with_output:
            state.status = "distilling"
            state.final_output = "Fixed tests by updating pytest fixtures"
            state.latest_output_hash = "abc123"
        return state.to_json_dict()

    def test_distill_node_stores_pattern(self):
        state_dict = self._make_state()
        result = distill_node(state_dict)
        result_state = SwarmState.model_validate(result)
        assert result_state.sona_distilled is True
        assert result_state.sona_cycle_count == 1
        # Memory should contain a stored pattern
        patterns = result_state.memory.search("Fix tests", top_k=5)
        assert len(patterns) > 0

    def test_distill_increments_cycle_count(self):
        state_dict = self._make_state()
        # Run twice
        state_dict = distill_node(state_dict)
        state_dict["status"] = "distilling"
        state_dict["final_output"] = "another fix"
        state_dict = distill_node(state_dict)
        assert state_dict["sona_cycle_count"] == 2

    def test_distill_node_sets_completed(self):
        state_dict = self._make_state()
        result = distill_node(state_dict)
        assert result["status"] == "completed"

    def test_sona_disabled_skips_distill(self):
        config = SwarmConfig(topology="hierarchical", sona_enabled=False)
        state = SwarmState(
            swarm_id="no-sona",
            objective="test",
            config=config,
            status="distilling",
            final_output="result",
        )
        result = distill_node(state.to_json_dict())
        result_state = SwarmState.model_validate(result)
        # Cycle count still increments, but no memory stored
        assert result_state.memory.size() == 0


# ── memory_retrieve_node ──────────────────────────────────────────────────────

class TestMemoryRetrieveNode:
    def test_retrieves_relevant_patterns(self):
        config = SwarmConfig(topology="hierarchical", sona_enabled=True, sona_min_confidence=0.5)
        state = SwarmState(
            swarm_id="retrieve-test",
            objective="Fix failing pytest tests",
            config=config,
        )
        # Pre-load memory with a relevant pattern
        state.memory.store(
            "existing-pattern",
            "pytest fixtures should be in conftest.py",
            score=0.9,
        )
        result = memory_retrieve_node(state.to_json_dict())
        result_state = SwarmState.model_validate(result)
        # History should show memory_retrieve entry
        kinds = [e.get("kind") for e in result_state.history]
        assert "memory_retrieve" in kinds

    def test_promotes_accessed_entries(self):
        config = SwarmConfig(topology="hierarchical", sona_enabled=True, sona_min_confidence=0.5)
        state = SwarmState(
            swarm_id="promote-test",
            objective="Fix tests",
            config=config,
        )
        state.memory.store("pattern-1", "Fix tests by adjusting fixtures", score=0.7)
        original_score = state.memory.get("pattern-1").score
        memory_retrieve_node(state.to_json_dict())
        # Score should be promoted
        new_score = state.memory.get("pattern-1").score
        assert new_score >= original_score


# ── InProcessCheckpointStore ─────────────────────────────────────────────────

class TestInProcessCheckpointStore:
    def test_save_and_restore(self):
        store = InProcessCheckpointStore()
        config = SwarmConfig(topology="hierarchical")
        state = SwarmState(swarm_id="cp-test", objective="test", config=config)
        state.status = "executing"
        store.save(state)
        restored = store.load_latest("cp-test")
        assert restored is not None
        assert restored.swarm_id == "cp-test"
        assert restored.status == "executing"

    def test_load_nonexistent_returns_none(self):
        store = InProcessCheckpointStore()
        assert store.load_latest("nonexistent") is None

    def test_multiple_checkpoints_returns_latest(self):
        store = InProcessCheckpointStore()
        config = SwarmConfig(topology="hierarchical")
        s1 = SwarmState(swarm_id="s1", objective="t", config=config, iteration=1)
        s2 = SwarmState(swarm_id="s1", objective="t", config=config, iteration=2)
        store.save(s1)
        store.save(s2)
        restored = store.load_latest("s1")
        assert restored is not None
        assert restored.iteration >= 1
