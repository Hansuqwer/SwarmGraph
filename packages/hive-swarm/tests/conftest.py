"""Shared fixtures (was missing — F-04A backlog item)."""

from __future__ import annotations

import pytest
from swarm.models.agent import AgentSpec, AgentVote, WorkerResult
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState


@pytest.fixture
def basic_config() -> SwarmConfig:
    return SwarmConfig(
        topology="hierarchical",
        consensus_protocol="raft",
        max_agents=8,
    )


@pytest.fixture
def basic_state(basic_config: SwarmConfig) -> SwarmState:
    return SwarmState(
        swarm_id="test-swarm",
        objective="Implement a simple add function",
        config=basic_config,
    )


@pytest.fixture
def make_vote():
    def _make(
        agent_id: str = "a1",
        agent_role: str = "coder",
        proposed_action: str = "do thing",
        confidence: float = 0.8,
    ) -> AgentVote:
        return AgentVote(
            agent_id=agent_id,
            agent_role=agent_role,
            proposed_action=proposed_action,
            confidence=confidence,
        )

    return _make


@pytest.fixture
def make_worker_result():
    def _make(
        agent_id: str = "a1",
        agent_role: str = "coder",
        task_id: str = "t1",
        success: bool = True,
        output: str = "ok",
        confidence: float = 0.9,
    ) -> WorkerResult:
        kwargs: dict = {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "task_id": task_id,
            "success": success,
            "confidence": confidence,
        }
        if success:
            kwargs["output"] = output
        else:
            kwargs["error_message"] = output or "failure"
        return WorkerResult(**kwargs)

    return _make
