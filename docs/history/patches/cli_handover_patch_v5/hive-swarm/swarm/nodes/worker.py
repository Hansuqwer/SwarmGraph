"""Worker node — patched (v5 — populates WorkerResult.usage).

History:
  F-16A: returns {"worker_results": [...]} for the operator.add reducer
  F-16B: collect_results_node calls swarm.mark_task_complete
  F-16-CORR1: confidence uses symmetric Jaccard
  v4: dispatcher-based execution (stub | gateway)
  v5: consumes dispatch_full → populates WorkerResult.usage from TokenUsage
"""
from __future__ import annotations

from typing import Any

from ..llm import (
    WorkerLLMError,
    build_dispatcher,
    resolve_llm_settings,
)
from ..models.agent import AgentState, TokenUsage, WorkerResult
from ..models.state import SwarmState


def _to_token_usage(resp: Any) -> TokenUsage | None:
    """Build a TokenUsage from a WorkerLLMResponse if any usage data is present."""
    if resp is None:
        return None
    in_t = getattr(resp, "input_tokens", 0) or 0
    out_t = getattr(resp, "output_tokens", 0) or 0
    model_id = getattr(resp, "model_id_used", "") or ""
    finish_reason = getattr(resp, "finish_reason", "") or ""
    provider_id = getattr(resp, "provider_id", "") or ""
    # Only emit a TokenUsage if there is *something* meaningful in it.
    if not any([in_t, out_t, model_id, finish_reason, provider_id]):
        return None
    return TokenUsage(
        input_tokens=in_t,
        output_tokens=out_t,
        model_id_used=model_id[:256],
        finish_reason=finish_reason[:64],
        provider_id=provider_id[:64],
    )


def worker_node(agent_state_dict: dict[str, Any]) -> dict[str, Any]:
    """LangGraph worker. Returns reducer-friendly {"worker_results": [...]}."""
    agent_state = AgentState.model_validate(agent_state_dict)
    agent_state.mark_started()

    try:
        settings = resolve_llm_settings(agent_state.task_context, agent_state.role)
        dispatcher = build_dispatcher(settings)

        # v5: dispatch_full returns rich WorkerLLMResponse with token counts
        resp = dispatcher.dispatch_full(
            role=agent_state.role,
            task_description=agent_state.task_description,
            context=agent_state.task_context,
        )
        output = resp.text
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
                "llm_latency_ms": getattr(resp, "latency_ms", 0),
            },
            usage=_to_token_usage(resp),     # v5
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

    return {"worker_results": [result.model_dump(mode="json")]}


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
                pass

    # v5: roll up token usage in history
    total_in = sum((r.usage.input_tokens if r.usage else 0) for r in swarm.worker_results)
    total_out = sum((r.usage.output_tokens if r.usage else 0) for r in swarm.worker_results)

    swarm.append_history("consensus", {
        "node": "collect_results",
        "vote_count": len(new_votes),
        "worker_count": len(swarm.worker_results),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
    })
    swarm.touch()
    return swarm.to_json_dict()


__all__ = ["worker_node", "collect_results_node", "_estimate_confidence", "_to_token_usage"]
