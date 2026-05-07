"""
AGENT 16 — Worker Node Specialist
Worker execution node — receives AgentState, produces WorkerResult.
Role-specific behavior dispatch. Structured output. Vote production.
"""
from __future__ import annotations

from typing import Any

from ..models.agent import AgentState, WorkerResult
from ..models.base import now_ts, stable_hash
from ..models.state import SwarmState


# ---------------------------------------------------------------------------
# Role-specific worker behaviors (stubs — replace with LLM calls)
# ---------------------------------------------------------------------------

def _execute_researcher(task_desc: str, context: dict[str, Any]) -> str:
    """Gather information, summarize requirements."""
    return f"[RESEARCHER] Analysis of: {task_desc[:100]}"


def _execute_architect(task_desc: str, context: dict[str, Any]) -> str:
    """Produce system design and module boundaries."""
    return f"[ARCHITECT] Design for: {task_desc[:100]}"


def _execute_coder(task_desc: str, context: dict[str, Any]) -> str:
    """Write the implementation."""
    return f"[CODER] Implementation for: {task_desc[:100]}"


def _execute_tester(task_desc: str, context: dict[str, Any]) -> str:
    """Write tests and validate the implementation."""
    return f"[TESTER] Test suite for: {task_desc[:100]}"


def _execute_reviewer(task_desc: str, context: dict[str, Any]) -> str:
    """Review code quality, security, correctness."""
    return f"[REVIEWER] Review for: {task_desc[:100]}"


def _execute_security(task_desc: str, context: dict[str, Any]) -> str:
    return f"[SECURITY] Security audit for: {task_desc[:100]}"


def _execute_optimizer(task_desc: str, context: dict[str, Any]) -> str:
    return f"[OPTIMIZER] Optimization analysis for: {task_desc[:100]}"


def _execute_coordinator(task_desc: str, context: dict[str, Any]) -> str:
    return f"[COORDINATOR] Coordination plan for: {task_desc[:100]}"


def _execute_default(task_desc: str, context: dict[str, Any]) -> str:
    return f"[AGENT] Output for: {task_desc[:100]}"


_ROLE_DISPATCH = {
    "researcher":  _execute_researcher,
    "architect":   _execute_architect,
    "coder":       _execute_coder,
    "tester":      _execute_tester,
    "reviewer":    _execute_reviewer,
    "security":    _execute_security,
    "optimizer":   _execute_optimizer,
    "coordinator": _execute_coordinator,
    "queen":       _execute_coordinator,
    "documenter":  _execute_default,
}


# ---------------------------------------------------------------------------
# Worker node
# ---------------------------------------------------------------------------

def worker_node(agent_state_dict: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph worker node. Receives an AgentState dict (via Send()).
    Executes role-specific logic. Returns WorkerResult dict for merge-back.

    This node does NOT have access to the full SwarmState — it only sees
    its own AgentState (isolation by design, per Ruflo worker model).
    """
    agent_state = AgentState.model_validate(agent_state_dict)
    agent_state.mark_started()

    try:
        executor = _ROLE_DISPATCH.get(agent_state.role, _execute_default)
        output = executor(agent_state.task_description, agent_state.task_context)
        confidence = _estimate_confidence(output, agent_state.task_description)
        agent_state.mark_done(output, confidence)

        result = WorkerResult(
            agent_id=agent_state.agent_id,
            agent_role=agent_state.role,
            task_id=agent_state.assigned_task_id or "unknown",
            success=True,
            output=output,
            confidence=confidence,
            duration_seconds=agent_state.duration_seconds() or 0.0,
        )
    except Exception as exc:
        agent_state.mark_failed(str(exc))
        result = WorkerResult(
            agent_id=agent_state.agent_id,
            agent_role=agent_state.role,
            task_id=agent_state.assigned_task_id or "unknown",
            success=False,
            error_message=str(exc),
            confidence=0.0,
            duration_seconds=agent_state.duration_seconds() or 0.0,
        )

    # Return as a dict that SwarmState can receive and merge
    return {
        "_worker_result": result.model_dump(mode="json"),
        "_agent_id": agent_state.agent_id,
    }


def _estimate_confidence(output: str, task_desc: str) -> float:
    """
    Heuristic confidence estimation.
    In production: use LLM self-evaluation or task-specific metrics.
    """
    if not output.strip():
        return 0.0
    task_tokens = set(task_desc.lower().split()[:20])
    out_tokens = set(output.lower().split())
    overlap = len(task_tokens & out_tokens) / max(len(task_tokens), 1)
    # Base confidence from output length
    length_score = min(len(output) / 500.0, 0.5)
    return round(min(1.0, overlap * 0.5 + length_score), 3)


# ---------------------------------------------------------------------------
# Merge-back node — called after all workers complete (fan-in)
# ---------------------------------------------------------------------------

def collect_results_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph fan-in node.
    Collects all worker results from state, converts to votes for consensus.
    """
    swarm = SwarmState.model_validate(state)
    swarm.status = "voting"

    # Convert worker results to votes
    new_votes = [r.to_vote() for r in swarm.worker_results]
    for vote in new_votes:
        swarm.collect_vote(vote)

    swarm.append_history("consensus", {
        "node": "collect_results",
        "vote_count": len(new_votes),
        "worker_count": len(swarm.worker_results),
    })
    swarm.touch()
    return swarm.to_json_dict()
