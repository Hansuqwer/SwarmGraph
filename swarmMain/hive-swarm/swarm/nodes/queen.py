"""
AGENT 15 — Queen Node Specialist
Objective decomposition + Send() fan-out to workers.
Supports all 5 topologies with topology-specific decomposition strategies.
"""
from __future__ import annotations

import secrets
from typing import Any

from ..models.agent import AgentSpec, AgentState
from ..models.state import SwarmState
from ..models.task import QueenDirective, SwarmTask
from ..models.types import AgentRole, SwarmTopology

try:
    from langgraph.types import Send
except ImportError:  # pragma: no cover
    Send = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Objective decomposition strategies
# ---------------------------------------------------------------------------

def _hierarchical_decompose(objective: str, max_agents: int) -> list[tuple[str, AgentRole]]:
    """
    Hierarchical strategy: break objective into role-specific sub-tasks.
    Returns list of (task_description, required_role).
    Ruflo: 'Queen → Coordinators → Workers'
    """
    roles: list[AgentRole] = ["researcher", "architect", "coder", "tester", "reviewer"]
    available = roles[: min(len(roles), max_agents)]
    tasks = []
    for role in available:
        desc = {
            "researcher": f"Research and gather context for: {objective}",
            "architect":  f"Design the solution architecture for: {objective}",
            "coder":      f"Implement the solution for: {objective}",
            "tester":     f"Write and validate tests for: {objective}",
            "reviewer":   f"Review the implementation for: {objective}",
        }.get(role, f"Handle {role} responsibilities for: {objective}")
        tasks.append((desc, role))
    return tasks


def _mesh_decompose(objective: str, max_agents: int) -> list[tuple[str, AgentRole]]:
    """
    Mesh: all agents get the same objective; peer-to-peer collaboration.
    Each produces their own output; gossip consensus merges them.
    """
    count = min(max_agents, 4)
    roles: list[AgentRole] = ["coder", "tester", "reviewer", "researcher"][:count]
    return [(f"Collaborate on: {objective}", role) for role in roles]


def _ring_decompose(objective: str, max_agents: int) -> list[tuple[str, AgentRole]]:
    """Ring: sequential pipeline — researcher → coder → tester → reviewer."""
    pipeline: list[tuple[str, AgentRole]] = [
        (f"Research and define requirements: {objective}", "researcher"),
        (f"Implement based on research: {objective}", "coder"),
        (f"Test the implementation: {objective}", "tester"),
        (f"Final review: {objective}", "reviewer"),
    ]
    return pipeline[: min(len(pipeline), max_agents)]


def _star_decompose(objective: str, max_agents: int) -> list[tuple[str, AgentRole]]:
    """Star: central hub routes to specialized spokes."""
    spokes: list[tuple[str, AgentRole]] = [
        (f"Security analysis for: {objective}", "security"),
        (f"Performance analysis for: {objective}", "optimizer"),
        (f"Architecture review for: {objective}", "architect"),
        (f"Implementation for: {objective}", "coder"),
    ]
    return spokes[: min(len(spokes), max_agents)]


_DECOMPOSE_FN = {
    "hierarchical": _hierarchical_decompose,
    "mesh":         _mesh_decompose,
    "ring":         _ring_decompose,
    "star":         _star_decompose,
    "adaptive":     _hierarchical_decompose,  # adaptive starts hierarchical
}


# ---------------------------------------------------------------------------
# Queen node — creates tasks + dispatches via Send()
# ---------------------------------------------------------------------------

def queen_node(state: dict[str, Any]) -> list[Any]:
    """
    LangGraph node.
    1. Decomposes the swarm objective into role-specific tasks.
    2. Registers AgentSpecs into state.
    3. Returns list[Send] for parallel worker fan-out.

    Ruflo: 'Queen → Send() fan-out → Workers (parallel)'
    """
    swarm = SwarmState.model_validate(state)
    swarm.status = "decomposing"
    swarm.iteration += 1

    if swarm.iteration > swarm.config.max_iterations:
        swarm.fail("max_iterations_exceeded", "Max swarm iterations exceeded")
        return [swarm.to_json_dict()]

    topology: SwarmTopology = swarm.config.topology
    decompose = _DECOMPOSE_FN[topology]
    sub_tasks = decompose(swarm.objective, swarm.config.max_agents)

    # Build SwarmTask list and AgentSpec list
    new_tasks: list[SwarmTask] = []
    new_agents: list[AgentSpec] = []
    send_list: list[Any] = []

    for idx, (desc, role) in enumerate(sub_tasks):
        agent_id = f"{role}-{idx + 1}"
        task_id = f"task-{swarm.iteration}-{idx + 1}"

        # Register agent
        spec = AgentSpec(agent_id=agent_id, name=agent_id, role=role)
        new_agents.append(spec)

        # Create task
        task = SwarmTask(
            task_id=task_id,
            description=desc,
            priority="high",
            assigned_to=agent_id,
            required_role=role,
        )
        task.assign(agent_id)
        new_tasks.append(task)

        # Build per-agent state for the worker node
        directive = QueenDirective(
            directive_id=f"dir-{task_id}",
            task=task,
            assigned_agent_id=agent_id,
            assigned_role=role,
            objective_hash=swarm.objective_hash,
            shared_context={"iteration": swarm.iteration, "objective": swarm.objective},
        )
        agent_state = AgentState(
            agent_id=agent_id,
            role=role,
            assigned_task_id=task_id,
            task_description=desc,
            task_context=directive.model_dump(mode="json"),
        )

        if Send is not None:
            send_list.append(Send("worker_node", agent_state.to_json_dict()))

    # Update swarm state (agents + tasks)
    swarm.agents = list(swarm.agents) + new_agents
    swarm.tasks = list(swarm.tasks) + new_tasks
    swarm.append_history("task_assigned", {
        "agent_count": len(new_agents),
        "task_ids": [t.task_id for t in new_tasks],
        "topology": topology,
    })
    swarm.touch()

    # Return Send() list for parallel dispatch
    # If LangGraph is unavailable, return plain state dict
    return send_list if send_list else [swarm.to_json_dict()]


# ---------------------------------------------------------------------------
# Fast/Medium agent stubs (Tier 1 and Tier 2 — no swarm needed)
# ---------------------------------------------------------------------------

def fast_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Tier 1: deterministic/heuristic transform — no LLM required.
    Ruflo: 'Agent Booster (WASM) — <1ms, $0'
    """
    swarm = SwarmState.model_validate(state)
    swarm.status = "executing"
    # In production: apply template-based transforms (var→const, add types, etc.)
    swarm.final_output = f"[FAST] Heuristic result for: {swarm.objective}"
    swarm.status = "completed"
    swarm.append_history("worker_result", {"tier": "tier1_fast", "agent": "fast_agent"})
    swarm.touch()
    return swarm.to_json_dict()


def medium_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Tier 2: single LLM call — no swarm spawn required.
    Ruflo: 'Haiku ~500ms, $0.0002'
    """
    swarm = SwarmState.model_validate(state)
    swarm.status = "executing"
    # In production: invoke model gateway with objective
    swarm.final_output = f"[MEDIUM] Single-agent result for: {swarm.objective}"
    swarm.status = "completed"
    swarm.append_history("worker_result", {"tier": "tier2_medium", "agent": "medium_agent"})
    swarm.touch()
    return swarm.to_json_dict()
