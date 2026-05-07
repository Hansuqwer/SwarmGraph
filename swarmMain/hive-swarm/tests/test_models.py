"""
AGENT 04 — Tactical Queen: Testing
AGENT 29 — Test Engineer

Test suite 1/5: Pydantic model correctness.
Covers: SwarmState, SwarmConfig, AgentSpec, AgentVote, WorkerResult,
        SwarmTask, SwarmMemory, SwarmCheckpoint.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from swarm.models.agent import AgentSpec, AgentState, AgentVote, WorkerResult
from swarm.models.base import stable_hash
from swarm.models.config import SwarmConfig
from swarm.models.memory import SwarmMemory, SwarmMemoryEntry
from swarm.models.state import SwarmCheckpoint, SwarmState, _MAX_ERRORS, _MAX_HISTORY
from swarm.models.task import QueenDirective, SwarmTask


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def base_config() -> SwarmConfig:
    return SwarmConfig(topology="hierarchical", max_agents=8)


@pytest.fixture
def base_state(base_config) -> SwarmState:
    return SwarmState(
        swarm_id="test-swarm-001",
        objective="Fix all failing pytest tests in the src/ directory",
        config=base_config,
    )


# ── SwarmState: extra='forbid' ────────────────────────────────────────────────

class TestSwarmStateExtraForbid:
    def test_unknown_field_rejected(self, base_config):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            SwarmState(
                swarm_id="s1",
                objective="task",
                config=base_config,
                injected_field="evil",
            )

    def test_model_validate_rejects_extra(self, base_config):
        data = {
            "swarm_id": "s1",
            "objective": "task",
            "config": base_config.model_dump(),
            "unknown_key": "bad",
        }
        with pytest.raises(ValidationError):
            SwarmState.model_validate(data)


# ── SwarmState: objective_hash ────────────────────────────────────────────────

class TestObjectiveHash:
    def test_hash_auto_computed(self, base_state):
        assert base_state.objective_hash != ""
        assert len(base_state.objective_hash) == 16

    def test_hash_is_stable(self, base_config):
        s1 = SwarmState(swarm_id="s1", objective="same obj", config=base_config)
        s2 = SwarmState(swarm_id="s2", objective="same obj", config=base_config)
        assert s1.objective_hash == s2.objective_hash

    def test_different_objectives_different_hashes(self, base_config):
        s1 = SwarmState(swarm_id="s1", objective="obj A", config=base_config)
        s2 = SwarmState(swarm_id="s2", objective="obj B", config=base_config)
        assert s1.objective_hash != s2.objective_hash


# ── SwarmState: bounded lists ─────────────────────────────────────────────────

class TestBoundedLists:
    def test_history_capped(self, base_config):
        big_history = [{"kind": "swarm_init", "ts": 0.0} for _ in range(_MAX_HISTORY + 50)]
        state = SwarmState(
            swarm_id="s1", objective="t", config=base_config, history=big_history
        )
        assert len(state.history) <= _MAX_HISTORY

    def test_errors_capped(self, base_config):
        many_errors = [f"err {i}" for i in range(_MAX_ERRORS + 20)]
        state = SwarmState(
            swarm_id="s1", objective="t", config=base_config, errors=many_errors
        )
        assert len(state.errors) <= _MAX_ERRORS

    def test_append_history_respects_cap(self, base_state):
        for i in range(_MAX_HISTORY + 10):
            base_state.append_history("swarm_init", {"i": i})
        assert len(base_state.history) <= _MAX_HISTORY


# ── SwarmConfig: frozen + validators ─────────────────────────────────────────

class TestSwarmConfig:
    def test_frozen_cannot_mutate(self, base_config):
        with pytest.raises(Exception):
            base_config.max_agents = 99  # type: ignore[misc]

    def test_tier_ordering_enforced(self):
        with pytest.raises(ValidationError, match="tier1_threshold"):
            SwarmConfig(tier1_threshold=0.6, tier2_threshold=0.4)

    def test_bft_quorum_1_rejected(self):
        with pytest.raises(ValidationError, match="defeats fault tolerance"):
            SwarmConfig(consensus_protocol="bft", bft_quorum_fraction=1.0)

    def test_complexity_tier_routing(self, base_config):
        assert base_config.complexity_tier(0.05) == "tier1_fast"
        assert base_config.complexity_tier(0.30) == "tier2_medium"
        assert base_config.complexity_tier(0.80) == "tier3_swarm"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            SwarmConfig(unknown_field="value")  # type: ignore[call-arg]


# ── AgentSpec ────────────────────────────────────────────────────────────────

class TestAgentSpec:
    def test_valid_agent_spec(self):
        spec = AgentSpec(agent_id="coder-1", name="Coder Agent", role="coder")
        assert spec.agent_id == "coder-1"
        assert spec.spawn_tag() == "coder:coder-1"

    def test_space_in_id_rejected(self):
        with pytest.raises(ValidationError, match="spaces"):
            AgentSpec(agent_id="bad id", name="n", role="coder")

    def test_frozen_after_creation(self):
        spec = AgentSpec(agent_id="a", name="n", role="coder")
        with pytest.raises(Exception):
            spec.role = "tester"  # type: ignore[misc]


# ── AgentVote ────────────────────────────────────────────────────────────────

class TestAgentVote:
    def test_confidence_bounds(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            AgentVote(agent_id="a", agent_role="coder", proposed_action="x", confidence=-0.1)
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            AgentVote(agent_id="a", agent_role="coder", proposed_action="x", confidence=1.5)

    def test_blank_action_rejected(self):
        with pytest.raises(ValidationError, match="blank"):
            AgentVote(agent_id="a", agent_role="coder", proposed_action="   ", confidence=0.8)


# ── WorkerResult ─────────────────────────────────────────────────────────────

class TestWorkerResult:
    def test_success_requires_output(self):
        with pytest.raises(ValidationError, match="non-empty output"):
            WorkerResult(
                agent_id="a", agent_role="coder", task_id="t1",
                success=True, output="",
            )

    def test_failure_requires_error_message(self):
        with pytest.raises(ValidationError, match="non-empty error_message"):
            WorkerResult(
                agent_id="a", agent_role="coder", task_id="t1",
                success=False, error_message="",
            )

    def test_output_hash_auto_computed(self):
        r = WorkerResult(
            agent_id="a", agent_role="coder", task_id="t1",
            success=True, output="some output", confidence=0.9,
        )
        assert r.output_hash == stable_hash("some output")

    def test_to_vote_conversion(self):
        r = WorkerResult(
            agent_id="a", agent_role="coder", task_id="t1",
            success=True, output="impl", confidence=0.8,
        )
        vote = r.to_vote()
        assert vote.agent_id == "a"
        assert vote.confidence == 0.8


# ── SwarmTask ────────────────────────────────────────────────────────────────

class TestSwarmTask:
    def test_task_lifecycle(self):
        task = SwarmTask(task_id="t1", description="Do work")
        assert task.status == "pending"
        task.assign("agent-1")
        assert task.status == "assigned"
        task.start()
        assert task.status == "running"
        assert task.attempts == 1
        task.complete("result here")
        assert task.status == "completed"
        assert task.result_hash != ""

    def test_cannot_assign_non_pending(self):
        task = SwarmTask(task_id="t1", description="x", status="failed")
        with pytest.raises(ValueError, match="Cannot assign"):
            task.assign("agent-1")

    def test_is_ready_with_no_deps(self):
        task = SwarmTask(task_id="t1", description="x")
        assert task.is_ready(set()) is True

    def test_is_ready_waits_for_deps(self):
        task = SwarmTask(task_id="t2", description="x", depends_on=["t1"])
        assert task.is_ready(set()) is False
        assert task.is_ready({"t1"}) is True


# ── SwarmMemory ───────────────────────────────────────────────────────────────

class TestSwarmMemory:
    def test_store_and_retrieve(self):
        mem = SwarmMemory()
        mem.store("key1", "value about testing", score=0.9)
        result = mem.get("key1")
        assert result is not None
        assert result.value == "value about testing"

    def test_search_returns_relevant(self):
        mem = SwarmMemory()
        mem.store("k1", "pytest testing framework", score=0.9)
        mem.store("k2", "database connection pooling", score=0.8)
        results = mem.search("pytest testing", top_k=3)
        assert len(results) > 0
        assert results[0].key == "k1"

    def test_distill_removes_low_score(self):
        mem = SwarmMemory(sona_min_score=0.7)
        mem.store("high", "good pattern", score=0.9)
        mem.store("low", "weak pattern", score=0.3)
        removed = mem.distill()
        assert any(e.key == "low" for e in removed)
        assert mem.get("high") is not None
        assert mem.get("low") is None

    def test_memory_bounded(self):
        mem = SwarmMemory(max_entries=5)
        for i in range(10):
            mem.store(f"key-{i}", f"value-{i}", score=float(i) / 10)
        assert mem.size() <= 5


# ── SwarmCheckpoint ───────────────────────────────────────────────────────────

class TestSwarmCheckpoint:
    def test_round_trip(self, base_state):
        cp = SwarmCheckpoint.from_state(base_state, "cp-1")
        restored = cp.restore()
        assert restored.swarm_id == base_state.swarm_id
        assert restored.objective == base_state.objective
        assert restored.objective_hash == base_state.objective_hash

    def test_checkpoint_preserves_status(self, base_state):
        base_state.status = "executing"
        cp = SwarmCheckpoint.from_state(base_state, "cp-2")
        assert cp.status_at_checkpoint == "executing"


# ── Anti-drift ───────────────────────────────────────────────────────────────

class TestAntiDrift:
    def test_aligned_output_passes(self, base_state):
        assert base_state.check_drift("Fix failing pytest tests in the src/ directory") is True

    def test_drifted_output_fails(self, base_state):
        assert base_state.check_drift("Unrelated content about cooking recipes") is False

    def test_assert_drift_raises(self, base_state):
        with pytest.raises(ValueError, match="Anti-drift"):
            base_state.assert_no_drift("content about unrelated topics entirely")

    def test_anti_drift_disabled_always_passes(self, base_config):
        cfg = SwarmConfig(
            topology="hierarchical",
            anti_drift_enabled=False,
        )
        state = SwarmState(swarm_id="s", objective="fix tests", config=cfg)
        assert state.check_drift("completely unrelated content") is True
