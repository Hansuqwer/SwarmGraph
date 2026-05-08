"""Queen + tier-1/tier-2 nodes — patched (v7).

History:
  v4–v6 lineage preserved.
  v7 — F-15-FWD1: `_llm_settings_from_config` now also forwards
       `stream_enabled` (from llm_stream_enabled) and
       `cost_tracking_enabled` (from cost_tracking_enabled). Without
       these, workers default to off regardless of SwarmConfig.
"""
from __future__ import annotations

from typing import Any

from ..llm import (
    WorkerLLMError,
    build_dispatcher,
    resolve_llm_settings,
)
from ..models.agent import AgentSpec, AgentState
from ..models.state import SwarmState
from ..models.task import QueenDirective, SwarmTask
from ..models.types import AgentRole, SwarmTopology

try:
    from langgraph.types import Send
    _HAS_SEND = True
except ImportError:  # pragma: no cover
    Send = None  # type: ignore[assignment,misc]
    _HAS_SEND = False


# ── Decomposition strategies (unchanged from v5) ──────────────────────────

def _hierarchical_decompose(objective, max_agents, *, prior_agreement=1.0):
    roles: list[AgentRole] = ["researcher", "architect", "coder", "tester", "reviewer"]
    available = roles[: min(len(roles), max_agents)]
    descs = {
        "researcher": f"Research and gather context for: {objective}",
        "architect": f"Design the solution architecture for: {objective}",
        "coder": f"Implement the solution for: {objective}",
        "tester": f"Write and validate tests for: {objective}",
        "reviewer": f"Review the implementation for: {objective}",
    }
    return [(descs.get(r, f"Handle {r} for: {objective}"), r) for r in available]


def _mesh_decompose(objective, max_agents, *, prior_agreement=1.0):
    perspectives: list[tuple[str, AgentRole]] = [
        (f"Implement the solution for: {objective}", "coder"),
        (f"Identify edge cases and corner-case tests for: {objective}", "tester"),
        (f"Critique potential pitfalls and risks in implementing: {objective}", "reviewer"),
        (f"Find prior art, libraries, and best practices for: {objective}", "researcher"),
    ]
    return perspectives[: min(len(perspectives), max_agents)]


def _ring_decompose(objective, max_agents, *, prior_agreement=1.0):
    pipeline: list[tuple[str, AgentRole]] = [
        (f"Research and define requirements: {objective}", "researcher"),
        (f"Implement based on research: {objective}", "coder"),
        (f"Test the implementation: {objective}", "tester"),
        (f"Final review: {objective}", "reviewer"),
    ]
    return pipeline[: min(len(pipeline), max_agents)]


def _star_decompose(objective, max_agents, *, prior_agreement=1.0):
    spokes: list[tuple[str, AgentRole]] = [
        (f"Security analysis for: {objective}", "security"),
        (f"Performance analysis for: {objective}", "optimizer"),
        (f"Architecture review for: {objective}", "architect"),
        (f"Implementation for: {objective}", "coder"),
    ]
    return spokes[: min(len(spokes), max_agents)]


def _adaptive_decompose(objective, max_agents, *, prior_agreement=1.0):
    if prior_agreement < 0.5:
        return _mesh_decompose(objective, max_agents, prior_agreement=prior_agreement)
    return _hierarchical_decompose(objective, max_agents, prior_agreement=prior_agreement)


_DECOMPOSE_FN = {
    "hierarchical": _hierarchical_decompose,
    "mesh": _mesh_decompose,
    "ring": _ring_decompose,
    "star": _star_decompose,
    "adaptive": _adaptive_decompose,
}


# ── F-15-FWD1: extract every relevant llm_* field from SwarmConfig ──────

def _llm_settings_from_config(config: Any) -> dict[str, Any]:
    """Pull every llm_* field off SwarmConfig.

    v7 — F-15-FWD1: stream_enabled + cost_tracking_enabled added.
    Defensive: missing attributes default to safe values so older configs
    still work.
    """
    return {
        "backend": getattr(config, "llm_backend", "stub"),
        "default_provider": getattr(config, "llm_default_provider", "9router"),
        "default_model": getattr(config, "llm_default_model", ""),
        "max_tokens": getattr(config, "llm_max_tokens", 512),
        "temperature": getattr(config, "llm_temperature", 0.0),
        "timeout_seconds": getattr(config, "llm_timeout_seconds", 60.0),
        "role_provider_overrides": dict(
            getattr(config, "llm_role_provider_overrides", {}) or {}
        ),
        "role_model_overrides": dict(
            getattr(config, "llm_role_model_overrides", {}) or {}
        ),
        "include_retrieved_patterns": getattr(config, "llm_include_retrieved_patterns", True),
        "include_objective": getattr(config, "llm_include_objective", True),
        # v7 — F-15-FWD1
        "stream_enabled": getattr(config, "llm_stream_enabled", False),
        "cost_tracking_enabled": getattr(config, "cost_tracking_enabled", True),
        # v8 — streaming guard settings
        "streaming_guard_patterns": list(
            getattr(config, "streaming_guard_patterns", None) or []
        ),
        "streaming_max_output_chars": getattr(config, "streaming_max_output_chars", 16384),
        "streaming_guard_check_every_n_chunks": getattr(
            config, "streaming_guard_check_every_n_chunks", 4
        ),
    }


# ── Queen node (unchanged) ───────────────────────────────────────────────

def queen_node(state: dict[str, Any]) -> list[Any]:
    swarm = SwarmState.model_validate(state)
    swarm.status = "decomposing"
    swarm.iteration += 1

    if swarm.iteration > swarm.config.max_iterations:
        swarm.fail("max_iterations_exceeded", "Max swarm iterations exceeded")
        return [swarm.to_json_dict()]

    topology: SwarmTopology = swarm.config.topology
    decompose = _DECOMPOSE_FN[topology]
    effective_max_agents = int(
        swarm.runtime_metadata.get("applied_agent_cap") or swarm.config.max_agents
    )
    effective_max_agents = max(1, min(effective_max_agents, swarm.config.max_agents))

    prior_agreement = (
        swarm.consensus_result.agreement_fraction
        if swarm.consensus_result else 1.0
    )
    sub_tasks = decompose(swarm.objective, effective_max_agents,
                          prior_agreement=prior_agreement)

    available_slots = effective_max_agents - len(swarm.agents)
    if len(sub_tasks) > available_slots:
        sub_tasks = sub_tasks[:available_slots]
        swarm.add_error(
            f"queen_node: truncated decomposition to {available_slots} tasks "
            f"(effective_max_agents={effective_max_agents})"
        )

    new_tasks: list[SwarmTask] = []
    new_agents: list[AgentSpec] = []
    send_list: list[Any] = []

    retrieved_patterns = list(swarm.retrieved_context) if swarm.retrieved_context else []
    llm_settings = _llm_settings_from_config(swarm.config)

    for idx, (desc, role) in enumerate(sub_tasks):
        agent_id = f"{role}-{idx + 1}"
        task_id = f"task-{swarm.iteration}-{idx + 1}"

        spec = AgentSpec(agent_id=agent_id, name=agent_id, role=role)
        new_agents.append(spec)

        task = SwarmTask(
            task_id=task_id, description=desc, priority="high",
            assigned_to=agent_id, required_role=role,
        )
        task.assign(agent_id)
        new_tasks.append(task)

        directive = QueenDirective(
            directive_id=f"dir-{task_id}",
            task=task,
            assigned_agent_id=agent_id,
            assigned_role=role,
            objective_hash=swarm.objective_hash,
            shared_context={
                "iteration": swarm.iteration,
                "objective": swarm.objective,
                "retrieved_patterns": retrieved_patterns,
                "llm_settings": llm_settings,
            },
        )
        agent_state = AgentState(
            agent_id=agent_id,
            role=role,
            assigned_task_id=task_id,
            task_description=desc,
            task_context=directive.model_dump(mode="json"),
        )

        if _HAS_SEND and Send is not None:
            send_list.append(Send("worker_node", agent_state.to_json_dict()))

    swarm.agents = list(swarm.agents) + new_agents
    swarm.tasks = list(swarm.tasks) + new_tasks
    swarm.append_history("task_assigned", {
        "agent_count": len(new_agents),
        "task_ids": [t.task_id for t in new_tasks],
        "topology": topology,
        "llm_backend": llm_settings.get("backend"),
        "llm_streamed": llm_settings.get("stream_enabled"),
        "llm_cost_tracked": llm_settings.get("cost_tracking_enabled"),
    })
    swarm.touch()

    if not _HAS_SEND or Send is None:
        if not send_list:
            return [swarm.to_json_dict()]
        raise RuntimeError(
            "langgraph.types.Send is unavailable but send_list is non-empty. "
            "Install langgraph>=0.3.0 to enable real fan-out."
        )

    return send_list


# ── Tier 1 (deterministic, unchanged) ────────────────────────────────────

def fast_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    swarm = SwarmState.model_validate(state)
    swarm.status = "executing"
    swarm.final_output = f"[FAST] Heuristic result for: {swarm.objective}"
    swarm.status = "completed"
    swarm.append_history("worker_result", {"tier": "tier1_fast", "agent": "fast_agent"})
    swarm.touch()
    return swarm.to_json_dict()


# ── Tier 2 (v5: through gateway) ─────────────────────────────────────────

def medium_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    swarm = SwarmState.model_validate(state)
    swarm.status = "executing"

    shared_context = {
        "iteration": swarm.iteration,
        "objective": swarm.objective,
        "retrieved_patterns": list(swarm.retrieved_context) if swarm.retrieved_context else [],
        "llm_settings": _llm_settings_from_config(swarm.config),
    }
    task_context = {"shared_context": shared_context}

    settings = resolve_llm_settings(task_context, role="coder")

    try:
        dispatcher = build_dispatcher(settings)
        resp = dispatcher.dispatch_full(
            role="coder",
            task_description=swarm.objective,
            context=task_context,
        )
        backend = settings.get("backend", "stub")
        if backend == "stub":
            swarm.final_output = f"[MEDIUM] Single-agent result for: {swarm.objective}"
        else:
            swarm.final_output = resp.text

        swarm.status = "completed"
        swarm.append_history("worker_result", {
            "tier": "tier2_medium",
            "agent": "medium_agent",
            "llm_backend": backend,
            "llm_provider": settings.get("effective_provider", ""),
            "input_tokens": getattr(resp, "input_tokens", 0),
            "output_tokens": getattr(resp, "output_tokens", 0),
        })
    except WorkerLLMError as exc:
        swarm.fail("model_error", f"medium_agent llm_error: {exc}")
        swarm.append_history("error", {"node": "medium_agent", "error": str(exc)})
    except Exception as exc:
        swarm.fail("model_error", f"medium_agent error: {exc}")
        swarm.append_history("error", {"node": "medium_agent", "error": str(exc)})

    swarm.touch()
    return swarm.to_json_dict()


__all__ = [
    "queen_node",
    "fast_agent_node",
    "medium_agent_node",
    "_DECOMPOSE_FN",
    "_llm_settings_from_config",
]
