"""Worker node — patched (v4 — gateway-aware).

History of patches on this file:
  F-16A (CRITICAL): worker returns {"worker_results": [WorkerResult]} so the
     reducer registered in factory.py merges parallel Send results correctly.
  F-16B: collect_results_node calls swarm.mark_task_complete for every successful result.
  F-16-CORR1: confidence uses symmetric Jaccard.
  v4 (this revision): role dispatch goes through swarm.llm.WorkerLLMDispatcher.
     Default backend is "stub" (deterministic, no network) — identical to
     pre-v4 output. When SwarmConfig.llm_backend == "gateway" (or env var
     HIVE_SWARM_LLM_BACKEND=gateway), workers route through
     ai-provider-swarm-gateway adapters.
"""
from __future__ import annotations

from typing import Any

from ..llm import (
    WorkerLLMError,
    build_dispatcher,
    resolve_llm_settings,
)
from ..models.agent import AgentState, WorkerResult
from ..models.state import SwarmState


# ── Worker node ──────────────────────────────────────────────────────────

def worker_node(agent_state_dict: dict[str, Any]) -> dict[str, Any]:
    """LangGraph worker. Returns reducer-friendly {"worker_results": [...]}."""
    agent_state = AgentState.model_validate(agent_state_dict)
    agent_state.mark_started()

    try:
        # Resolve effective settings: env > queen-forwarded > defaults
        settings = resolve_llm_settings(agent_state.task_context, agent_state.role)
        dispatcher = build_dispatcher(settings)

        output = dispatcher.dispatch(
            role=agent_state.role,
            task_description=agent_state.task_description,
            context=agent_state.task_context,
        )
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
            metadata={
                "llm_backend": settings.get("backend", "stub"),
                "llm_provider": settings.get("effective_provider", ""),
            },
        )
    except WorkerLLMError as exc:
        agent_state.mark_failed(f"llm_error: {exc}")
        result = WorkerResult(
            agent_id=agent_state.agent_id,
            agent_role=agent_state.role,
            task_id=agent_state.assigned_task_id or "unknown",
            success=False,
            error_message=f"llm_error: {exc}",
            confidence=0.0,
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

    # F-16A: reducer-friendly return shape
    return {"worker_results": [result.model_dump(mode="json")]}


# ── Confidence helper ────────────────────────────────────────────────────

def _estimate_confidence(output: str, task_desc: str) -> float:
    """Symmetric Jaccard over full token sets (F-16-CORR1)."""
    if not output.strip():
        return 0.0
    task_tokens = set(task_desc.lower().split())
    out_tokens = set(output.lower().split())
    union = task_tokens | out_tokens
    overlap = len(task_tokens & out_tokens) / max(len(union), 1)
    length_score = min(len(output) / 500.0, 0.5)
    return round(min(1.0, overlap * 0.5 + length_score), 3)


# ── Fan-in node ──────────────────────────────────────────────────────────

def collect_results_node(state: dict[str, Any]) -> dict[str, Any]:
    """Convert worker results to votes; mark tasks complete (F-16B)."""
    swarm = SwarmState.model_validate(state)
    swarm.status = "voting"

    new_votes = [r.to_vote(round_id=swarm.consensus_round_id) for r in swarm.worker_results]
    for vote in new_votes:
        swarm.collect_vote(vote)

    for r in swarm.worker_results:
        if r.success:
            try:
                swarm.mark_task_complete(r.task_id, r.output)
            except ValueError:
                pass  # task may already be in a non-pending state on retry

    swarm.append_history("consensus", {
        "node": "collect_results",
        "vote_count": len(new_votes),
        "worker_count": len(swarm.worker_results),
    })
    swarm.touch()
    return swarm.to_json_dict()


__all__ = ["worker_node", "collect_results_node", "_estimate_confidence"]
