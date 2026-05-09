"""Model tests."""

import pytest
from pydantic import ValidationError
from swarm.models.agent import AgentSpec, AgentVote, WorkerResult
from swarm.models.config import SwarmConfig
from swarm.models.task import SwarmTask
from swarm.models.types import QUEEN_NODE_NAMES


def test_agent_spec_rejects_spaces():
    with pytest.raises(ValidationError):
        AgentSpec(agent_id="bad id", name="x", role="coder")


def test_agent_spec_frozen():
    spec = AgentSpec(agent_id="a1", name="alice", role="coder")
    with pytest.raises(ValidationError):
        spec.role = "tester"  # type: ignore[misc]


def test_agent_vote_blank_action_rejected():
    with pytest.raises(ValidationError):
        AgentVote(agent_id="a1", agent_role="coder", proposed_action="   ", confidence=0.5)


def test_worker_result_success_requires_output():
    with pytest.raises(ValidationError):
        WorkerResult(agent_id="a1", agent_role="coder", task_id="t1", success=True, output="")


def test_worker_result_failure_requires_error():
    with pytest.raises(ValidationError):
        WorkerResult(
            agent_id="a1", agent_role="coder", task_id="t1", success=False, error_message=""
        )


def test_worker_result_recomputes_output_hash():
    """F-07A: caller-provided hash is overwritten."""
    r = WorkerResult(
        agent_id="a1",
        agent_role="coder",
        task_id="t1",
        success=True,
        output="hello",
        output_hash="WRONG_HASH",
    )
    assert r.output_hash != "WRONG_HASH"
    assert len(r.output_hash) == 16


def test_swarm_config_tier_ordering_enforced():
    with pytest.raises(ValidationError):
        SwarmConfig(tier1_threshold=0.6, tier2_threshold=0.5)


def test_swarm_config_bft_quorum_lower_bound():
    """F-10A: was ge=0.51, now ge=0.667."""
    with pytest.raises(ValidationError):
        SwarmConfig(bft_quorum_fraction=0.6)


def test_swarm_config_bft_quorum_unanimity_rejected_for_bft():
    with pytest.raises(ValidationError):
        SwarmConfig(consensus_protocol="bft", bft_quorum_fraction=1.0)


def test_swarm_config_memory_namespace_charset():
    """F-10-T1: traversal-style names rejected."""
    with pytest.raises(ValidationError):
        SwarmConfig(memory_namespace="../escape")


def test_swarm_task_no_self_dep():
    """F-08A: was missing — depends_on cannot include task_id."""
    with pytest.raises(ValidationError):
        SwarmTask(task_id="t1", description="x", depends_on=["t1"])


def test_swarm_task_dedupe_deps():
    t = SwarmTask(task_id="t1", description="x", depends_on=["a", "a", "b", "a"])
    assert t.depends_on == ["a", "b"]


def test_swarm_task_fail_empty_reason_rejected():
    """F-08B."""
    t = SwarmTask(task_id="t1", description="x")
    with pytest.raises(ValueError):
        t.fail("")


def test_swarm_task_lifecycle():
    t = SwarmTask(task_id="t1", description="x")
    t.assign("a1")
    assert t.status == "assigned"
    t.start()
    assert t.status == "running"
    assert t.attempts == 1
    t.complete("done!")
    assert t.status == "completed"
    assert t.result_summary == "done!"
    assert t.result_hash != ""


def test_queen_node_names_centralized():
    """F-13C: single source of truth for queen names."""
    assert "hierarchical" in QUEEN_NODE_NAMES
    assert QUEEN_NODE_NAMES["hierarchical"] == "hierarchical_queen"
    assert len(QUEEN_NODE_NAMES) == 5
